# Loop8 daily dashboard

Two pages:

- **[Sep 10–14 report](https://olga-leyman.github.io/loop8-daily-dashboard/report.html)** — send this link to your boss
- **[Daily dashboard](https://olga-leyman.github.io/loop8-daily-dashboard/)** — rolling last-5-days stats

A GitHub Action runs every day at 8:00am Pacific, pulls Klaviyo (installs, registrations, trials, desktop sync, password import, Tru8, live email/push), and updates `data/latest.json`. Paid-ad spend stays on the weekly report until the next manual pull.

Anyone with the link can open the pages. Do not put API keys in this repo.
