import requests
import argparse
from bs4 import BeautifulSoup
import re
import datetime
import json
import time
import pandas as pd
import os
import numpy as np
from twilio.rest import Client

MESSAGE_CACHE = "message_cache.txt"
SAMPLE_AJAX_FILES = ["samples/sample-ajax.json", "samples/sample-ajax-2.json"]
pd.set_option("max_colwidth", 1000)

# Where are we?
def relative_path(name):
    try:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    except:
        return os.path.join(os.getcwd(), name)

class LoginError(Exception):
    """Exception raised for errors in the input.

    Attributes:
    """

    def __init__(self, message):
        self.message = message
        pass

class AspcaScraper:

    def __init__(self, debug=False, local=False):
        self.local = local
        self.debug = debug
        self.logged_in = False
        self.logged_in_session = None
        self.log("Initializing scraper")

    def session(self):
        if self.local:
            self.log("Local, skipping login")
            return
        elif self.logged_in_session:
            self.log("Session request, already logged in")
            return self.logged_in_session
        else:
            self.log("Session request, need to log in")
            self.logged_in_session = self.log_in()
            return self.logged_in_session

    def log_in(self):
        self.log("Logging in")

        # Visit the homepage with a new session
        session = requests.Session()
        session.get('https://aspcasnc.civicore.com/RSS/index.php?action=userLogin')

        # Actually do the logging in        
        target_url = 'https://aspcasnc.civicore.com/RSS/?ajaxRequest=0'
        data = {
            'fieldValues[]': [
                os.getenv('ASPCA_USERNAME'),
                os.getenv('ASPCA_PASSWORD'),
                '',
                '_fw_PasswordNotSetThisTime'
            ],
            'login_id': 4,
            'loginBoxNumber': 0,
            'ajaxFunction': 'login',
            'ajaxReturnType': 'json'
        }
        response = session.post(target_url, data=data)

        if response.json()['status'] == 'success':
            self.log("Login successful")
            return session
        else:
            self.warn(f"Login unsuccessful, response was {response.text}")
            raise LoginError(f"Failed to log in with response {response.text}")

    def ajax_urls(self):
        self.log("Grabbing the AJAX urls from the calendar page")
        response = self.session().get('https://aspcasnc.civicore.com/RSS/index.php?section=eventCal&action=cal')

        ajax_paths = re.findall('index.php\?ajaxRequest=\d+\&ajaxFunction=getEvents', response.text)

        base = 'https://aspcasnc.civicore.com/RSS/'

        def build_ajax_url(path):
            # From yesterday to 120 days in the future
            start_dt = datetime.datetime.today() - datetime.timedelta(days=1)
            start = int(time.mktime(start_dt.timetuple()))
            end_dt = datetime.datetime.today() + datetime.timedelta(days=120)
            end = int(time.mktime(end_dt.timetuple()))
            url = '{base}{path}&start={start}&end={end}'.format(base=base, path=path, end=end, start=start)
            return url

        urls = [build_ajax_url(ajax_path) for ajax_path in ajax_paths]

        self.log("Found AJAX urls:")
        for url in urls:
            self.log(f"\t{url}")
        return urls

    def get_ajax_data(self):
        if self.local:
            return [json.load(open(file)) for file in SAMPLE_AJAX_FILES]
        else:
            return [self.session().get(url).json() for url in self.ajax_urls()]

    def results_as_df(self):
        daily_details = self.get_ajax_data()
        try:
            df = pd.concat([pd.DataFrame(d) for d in daily_details], sort=True).reset_index(drop=True)
        except:
            df = pd.concat([pd.DataFrame(d) for d in daily_details]).reset_index(drop=True)
        df.set_index('id', inplace=True)

        def get_title(doc):
            self.log(f"Working on {doc}")
            try:
                return doc.find("br").previous_sibling.strip()
            except AttributeError:
                self.log(f"Failed to find title in {doc}")
                return np.nan

        self.log(f"Data looks like \n{df}")

        parsed = df.title.apply(self.extract_row_data)
        parsed['date'] = pd.to_datetime(df.end, format="%Y-%m-%dT00:00:00%z", exact=False)
        parsed.dropna(inplace=True)
        self.log(f"Parsed shape is {parsed.shape}")

        self.log(f"Cleaned data looks like\n{parsed}")
        return parsed

    # Splitting "Total Open Appts/Max # of Cats: 1"
    def extract_row_data(self, content):
        self.log(f"Extracting useful information from '{content}'")

        doc = BeautifulSoup(content, 'html.parser')
        try:
            location = doc.find("br").previous_sibling.strip()

            result = {
                'location': location
            }
            listings = doc.find("br").next_siblings
            for listing in listings:
                details = listing.string.strip().split(": ")
                result[details[0]] = details[1]
            return pd.Series(result)
        except AttributeError:
            self.log(f"Failed extraction")
            return pd.Series({'location': np.nan})

    def scrape(self):
        self.log("Scraping")
        results = self.results_as_df()

        # Add a placeholder so we know we did something at this time
        placeholder = pd.DataFrame([{'location': 'placeholder'}])
        results = pd.concat([results, placeholder], sort=False)

        # Note the time we scraped it
        results['collected_at'] = datetime.datetime.now()

        # Anything empty - no cats, dogs, etc - gets a 0
        results.fillna(0, inplace=True)
        self.results = results

        self.write_to_disk()

    def write_to_disk(self, filename="transports.csv"):
        self.log(f"Writing to disk as {filename}")
        self.log(f"Data to write looks like \n {self.results}")

        # Save into compendium file
        try:
            old = pd.read_csv(relative_path(filename))
        except FileNotFoundError:
            old = pd.DataFrame({})
        total = pd.concat([old, self.results], sort=False)
        total.to_csv(relative_path(filename), index=False)

    def compose(self, df):
        def row_to_message(row):
            date_str = row['date'].strftime("%-m/%d %a")
            text = f"{row['location']}\n{date_str}"
            for key in row.keys():
                if key not in ['date', 'location', 'collected_at']:
                    if int(row[key]) > 0:
                        text = f"{text}\n  * {key}: {row[key]}"
            return text

        # Convert each row into a message, then put one on each line
        messages = df.apply(row_to_message, axis=1)
        msg = '\n-\n'.join(messages.values)
        msg = msg.replace("Total Open Appts/", "")
        msg = msg.replace("Max # of ", "")
        msg = re.sub(r"^[A-Z ]*?: ", "", msg, flags=re.M)
        # link_url = 'https://aspcasnc.civicore.com/RSS/index.php?section=eventCal&action=cal'
        link_url = 'https://bit.ly/2I7fT72'
        message_text = f"{msg}\n\nSignup: {link_url}"

        self.log(f"Message text is:\n{message_text}")
        return message_text

    def notify(self):
        not_placeholder = self.results.location != 'placeholder'
        curious = self.results[not_placeholder]
        if curious.empty:
            self.log("Nothing to notify about")
            return

        self.log("Notifying")

        text = self.compose(self.results[not_placeholder])
        self.send_message(text)

    def send_message(self, message_text):
        try:
            with open(MESSAGE_CACHE) as file:
                last_message = file.read()
        except:
            last_message = ""

        if last_message == message_text:
            self.log("Current message same as last message, skipping")
            return
        else:
            self.log("Message is NOT the same as the last message")

        account_sid = os.getenv('TWILIO_CR_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_CR_AUTH_TOKEN')
        service_sid = os.getenv('TWILIO_CR_SERVICE_SID')

        dated_text = f"{datetime.datetime.now().strftime('%b %d %I:%M%p')}\n\n{message_text}"

        self.log(f"Sending through Twilio, message text is \n{dated_text}")

        client = Client(account_sid, auth_token)
        message = client.notify.services(service_sid).notifications.create(
            tag="sms",
            body=dated_text)

        self.log("Caching text")
        with open(MESSAGE_CACHE, "w") as file:
            file.write(message_text) 

    def write(self):
        pass

    def warn(self, message):
        self.log(message, level='WARN')

    def log(self, message, level='LOG'):
        if self.debug:
            indented = message.replace('\n', '\n            ')
            print(f'{level:>10}: {indented}')

parser = argparse.ArgumentParser(description='Scrape the ASPCA website for cat transport stuff.')
parser.add_argument('--notify', action='store_true')
args = parser.parse_args()

scraper = AspcaScraper(debug=False, local=False)
scraper.scrape()
if args.notify:
    scraper.notify()
