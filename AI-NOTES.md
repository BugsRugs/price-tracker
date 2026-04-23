# AI Notes
 
I used Claude Code heavily on this project, probably for most of the typing. The interesting part isn't where it helped. It's where it got things wrong and how I caught them. Two misses stood out, both in the scraper.
 
## Miss 1: the first HTTP client didn't work
 
The agent scaffolded the scraper with `httpx`, which is a reasonable default. Web scraping is new to me, so when every request came back blocked, my first instinct was to assume my code was wrong. I went through my headers, my User-Agent, my selectors. None of it mattered, every request was being flagged before Amazon even looked at the page I asked for.
 
What I eventually figured out: the block wasn't happening because of anything in my request, it was happening because of the HTTP client itself. Amazon can tell the difference between a request from a real browser and a request from a Python script at a lower level than the one I was working at. `httpx` sends a fingerprint that gets recognized as non-browser traffic, and there's nothing you can change in your headers to fix that.
 
The fix was swapping to `curl_cffi`, a library that makes Python requests look like they're coming from a real Chrome browser. After the swap, the same code worked on the first try.
 
**What I'd take from this:** when the agent suggests fixes inside a layer (more headers, different User-Agent, retry logic) and none of them work, the problem is probably not inside that layer. I don't fully understand the mechanics of how Amazon detects this, I know it happens below the HTTP level and I know the fix is a library that impersonates a browser, and that was enough to solve the problem. I'd want to read more about it if this were my job.
 
## Miss 2: the selectors looked right but didn't find prices
 
The agent wrote the price extractor using `.a-offscreen`, which is the CSS class Amazon uses on its visible price elements. I looked at a product page in my browser and the selector matched. It seemed right.
 
In practice, the selector kept coming back with nothing. For a while I thought my HTTP client was returning partial pages, or that Amazon was serving me something different from what I saw in my browser.
 
The thing I eventually tried: instead of looking at the page the way my browser showed it, I looked at the raw response my scraper was getting. The price wasn't in the element I expected, it was sitting in a JSON blob inside a `<script>` tag further up the page. That version of the price was always there. The visible one gets filled in by JavaScript after the page loads, which my scraper wasn't running.
 
The fix was to fall back on a regex that pulls the price out of the JSON blob when the CSS selector comes back empty. It's uglier than just using a selector, but it works reliably across all three products I'm tracking.
 
**What I'd take from this:** the browser and the scraper don't see the same page. What looks like the right selector in DevTools can be completely wrong in the raw HTML. Next time I'd start by looking at the raw response before trusting anything I see in the browser.
 
I also caught a second-order bug while debugging this: my error-handling code was treating "we found a price but it was bad" and "we never found a price at all" as the same error. That made the real problem hide. I split them into two different error types so the logs actually tell me what's going on. Small fix, but I wouldn't have found it without the first bug.
 
## Known limits I didn't fix
 
The scraper works on normal product pages, but I know there are cases where it won't:
 
- Products with multiple variants (size, color) often show a zero price until you click one, because the real price is filled in by JavaScript. My scraper doesn't run JavaScript.
- Some products put the price in different JSON shapes than the one my regex looks for. My regex only catches the common case.
- The fallback selector I use as a last resort can sometimes match a crossed-out "list price" instead of the real sale price.
I didn't fix any of these because each would take real time and I'm tracking three specific products that don't have these problems. If I were building this for real, I'd use a browser automation tool like Playwright that runs JavaScript, or pull from Amazon's structured data blocks (which are more stable than the HTML), or pay for a service that handles all of this. All three add complexity.
 
## Bot detection and timing
 
The demo is set to check prices every minute so a reviewer can see notifications fire quickly. I learned the hard way that this is exactly what bot detection looks for, regular, predictable traffic. For a real deployment I'd check every 15–30 minutes, add random jitter to the interval so checks don't happen at exactly the same time, and space out the products inside a single check so they don't all fire at once. None of that is in the code because the whole point of a 1-minute interval is to make testing fast.
 
## What I learned about working with the agent
 
Two things:
 
**The agent writes code that looks right.** In both cases above, the code it wrote was the kind of code I would have written if I were more experienced, reasonable library, standard selectors, conventional patterns. The problem wasn't that the code was sloppy. It's that the problem was somewhere the agent couldn't see from the code alone. Reviewing generated code against "does this look right" would have let both bugs through. What caught them was running the thing against the real Amazon and noticing it wasn't working.
 
**Being new to a domain is a reason to slow down, not speed up.** I used the agent mainly because I wanted to move fast, but the two times I got stuck, I got unstuck by slowing down, reading the raw response instead of trusting the browser view, questioning the library itself instead of tweaking its inputs. The agent is good at making me fast on things I understand. For things I don't understand yet, it can be fast in the wrong direction.
