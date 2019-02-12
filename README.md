# ASPCA TNR Appointment Scraper/Notifier

**Get notified via text message when spots open/close on the ASPCA calendar.**

Also track how many spots are open over time, so you can get grumpy about people dumping everything at 10am the day before.

> This is the **DIY technical setup** for this service. If you'd just like to subscribe, text `SUBSCRIBE` to `347-960-4494`.

## Life Setup

First, you'll need an account with the ASPCA. You get this by become TNR (trap-neuter-release) certified. A class in real life helps you meet actual folks who you can work with, but [the online version works just fine, too](http://bit.ly/TNRCertOnlineNYC).

Next, you'll need to set up your bulk SMS service. You'll need three services from Twilio - Programmable SMS + Notify + Runtime - but [this video walks you through the setup](https://www.youtube.com/watch?v=qnrtIUBlnzk).

## Tech setup

This tool needs **five** environment variables

* Your ASPCA login information: `ASPCA_USERNAME` and `ASPCA_PASSWORD`
* Twilio service information: `TWILIO_CR_ACCOUNT_SID`, `TWILIO_CR_AUTH_TOKEN`, and `TWILIO_CR_SERVICE_SID`

We use [pipenv](https://pipenv.readthedocs.io/en/latest/) to keep dependencies easy. To install and run:

```
pipenv install
pipenv shell
python aspca.py --notify
```
