# Design Notes
 
This is a 4-hour take-home, so my priorities were: a reviewer should be able to clone the repo and run it with no setup, each piece of the system should be testable on its own, and I should be honest about the tradeoffs I'm making. Below are the decisions worth explaining and the things I deliberately didn't build.
 
## Notifications
 
The system supports two notification channels: one that logs to the terminal and one that sends a desktop notification. Both work without any setup, a reviewer doesn't need to sign up for Slack or configure email just to verify the thing works. Both channels live behind a small interface (a Python Protocol with one method, `send(event)`), and there's a wrapper that chains multiple channels together so one failing doesn't stop the others.
 
Adding a real network channel like Slack or email would need one small change. Right now the config just takes a list of channel names, a channel like Slack needs a URL to post to, which means the config has to carry more than a name. That's a small refactor, the existing channels wouldn't break.
 
**The bigger gap:** my `send` method doesn't return anything. If a notification silently fails inside the channel, the rest of the system doesn't know. That's fine for the two local channels I have, because if they fail I can see it in the logs. For a Slack notification, I'd want the method to return a result so the scheduler could decide whether to retry.
 
**Principle:** build the interface for the channels you actually have, not the ones you imagine. It's easier to extend a small working interface than to simplify an oversized one.
 
## Storage: SQLite instead of Postgres
 
Two reasons I picked SQLite.
 
First, the reviewer doesn't have to install anything. SQLite is just a file. Postgres would mean running a separate database server, which is more setup than the size of this project justifies.
 
Second, this whole app runs as one process. The scheduler and the web dashboard are the same Python program, sharing one database. Postgres solves problems I don't have, it's the right choice when you have multiple programs writing to the same database, or when the app runs across multiple machines. Neither of those applies here.
 
I did turn on SQLite's WAL mode, which lets the dashboard read old price history at the same time the scheduler is writing a new price check, instead of one blocking the other. That matters because a single price check can take 5–15 seconds, and I didn't want the dashboard to freeze during one.
 
**When I'd switch to Postgres:** if the app grew to multiple scraper processes writing to the same database, or ran across multiple machines. At three products checked once an hour, nothing about this app stresses SQLite.
 
**Principle:** pick the database that fits the shape of the deployment, not the one that scales furthest. You can always migrate; you can't un-install Postgres from a reviewer's laptop.
 
## Logging
 
I used Python's standard `logging` library with a small custom formatter that turns structured data into readable key-value pairs. A log line looks like `check_completed check_id=83 product_id=1 status=ok price=59.99`.
 
This is easy to read in a terminal and easy to search with `grep`. A more formal approach would output JSON, which is better if you're sending logs to a central system that parses them automatically. But for a project where the main reader of logs is a person looking at their terminal, readability wins.
 
If I wanted to ship logs to something like Datadog later, it's one change — replace my formatter with a JSON one. The places in the code that call `log.info(...)` wouldn't have to change at all.
 
**Principle:** optimize the format for the person actually reading it. Right now that's a human at a terminal.
 
## Config file instead of environment variables
 
Product URLs and thresholds live in `config.yaml`. Environment variables are the usual alternative, and they're better for some things, they compose well with containers and secret management tools. But trying to write a list of product URLs as environment variables gets ugly fast (`PRODUCT_0_URL`, `PRODUCT_1_URL`, etc.), and YAML is the natural shape for a list.
 
To keep secrets out of the repo, I gitignore `config.yaml` and commit a `config.example.yaml` with placeholder values. There are no secrets in the current config, but if I added a Slack webhook or an SMTP password, I'd read those from environment variables and leave the non-sensitive settings in YAML.
 
**Principle:** use the file format that matches the shape of the data, and keep secrets out of both the repo and the file the reviewer copies.
 
## Scraping strategy and Amazon's terms of service
 
This is the tradeoff I thought about the most, and the one I'm least comfortable with.
 
There were three paths:
1. Scrape Amazon pages directly.
2. Pay for a third-party API that does the scraping for me (Keepa, Rainforest API).
3. Use Amazon's official Product Advertising API, which requires an Associates account.
I picked option 1 because the reviewer shouldn't have to sign up for a service just to run my demo. The issue is that Amazon's terms of service forbid automated scraping, and the library I ended up using (`curl_cffi`) specifically gets around the controls Amazon uses to enforce that rule. I know this isn't compliant. I used it because I was getting blocked with a normal HTTP client and this was the fastest way to a working demo.
 
If I were actually deploying this, I'd use option 2 (the third-party API handles the legal side and resells the data) or option 3 if the product qualified. My scraper is isolated in one file, so swapping it for a compliant source is a single-file change. The rest of the system, storage, detection, notification doesn't care where the price comes from.
 
**Principle:** when you have to make a choice that isn't production-ready, name it out loud and design the system so the compliant version is a drop-in replacement.

## Final Touches
In the last 30 minutes I attempted to achieve one of the stretch goals but found after building a plan for the REST export and implementing it I ran into regression errors. The REST export would work properly when curl testing but the dashboard showing 30 day price history would fail and show 'loading' the entire time. After two failed attempts I made the decision to not pursue this further and focus more on making the scraping more robust. 

I added three techniques to scrape more successfully, adding random time after each scrape to the next time we scrape, changing out headers such as mozilla, chrome, etc, and changing the order of products I scraped. This resulted in far more succesfuly price grabs and making the system overall more accurate and robust since obtaining the price itself if the backbone of the project. 
 
## What I deliberately didn't build
 
**Retrying after getting blocked by bot detection.** When Amazon shows a CAPTCHA, my scraper records it as `status=bot_detected` and moves on. Retrying right away would hit the same block, so there's no point. The real solution is to wait, and the scheduler's normal interval already does that. A better production version would add random timing so the traffic looks less predictable, I didn't build that because the 1-minute interval I use for testing makes any pattern visible anyway.
 
**Telling the scheduler whether a notification actually got delivered.** See the notifications section. Fine for the local channels I have; would need to change for a real network channel.
 
**Surviving a crash between sending a notification and recording it.** If the app crashes in that narrow window, it might send the same notification twice when it restarts. The fix is to record the intent to send first, then mark it sent after. The brief lists this as a stretch goal, and I left it there.
 
**Cleaning up SQLite's write-ahead log on startup.** SQLite handles this automatically most of the time, but a very long-running process can let the log grow larger than ideal. One line of code fixes it. I didn't add it because at three products checked once an hour, this app writes a few dozen rows per day — nowhere near the size where it would matter.
 
**Principle for all four:** don't build for problems you don't have yet. Name them, explain why they don't apply at this scale, and move on.
 
