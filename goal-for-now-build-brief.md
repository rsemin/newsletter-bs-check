# Build brief: ship a small tool to production, myself

## Why this build exists
I'm preparing for a technical interview with a startup CTO, a systems engineer who has built search. My biggest gap is production experience: I've designed and shipped AI systems, but always inside someone else's managed platform. I've never owned a deploy, read my own logs after something broke, or rolled back a bad release.

**The tool is not the point. The deploy loop is.** The goal is to come out of this afternoon with true, first-hand answers to "how do you test, deploy and debug what you build?", not a polished product.

## Time box
About 2.5 hours. If time runs short, cut features before cutting deployment. A trivial app that is properly deployed beats a rich app running on my laptop.

## How we split the work
- **You (Claude) write the application code** and any config files, and explain what each file does in a sentence or two.
- **I run every deploy step myself**, read every error myself, and decide the fix. Don't do the deploy for me, and don't pre-empt errors I should hit and read.
- When something breaks, **ask me what I think is wrong before telling me.** Point me to where to look (logs, status codes, environment) rather than handing me the answer.
- Before each step, tell me in one line what it proves and what could go wrong.

## Done means
1. **It runs somewhere other than my laptop**, reachable at a URL.
2. **Pushing to the main branch deploys it** automatically.
3. **Automated tests run on every push**, and a failing test stops a bad version going live.
4. **No secrets in the repo.** Configuration comes from the environment.
5. **A health check** tells me whether it's up and whether its dependencies are reachable.
6. **Logs I can actually use:** structured, with an ID per request, findable on the host.
7. **Data survives a redeploy.**
8. **Safe to retry:** if the same request or event arrives twice, nothing is duplicated.
9. **I broke it on purpose and recovered.** At minimum: deployed a bad version and rolled back; sent malformed input; cut a dependency. For each, I wrote five lines: what broke, how I noticed, what I changed.

## Priority if time runs short
- **Must:** 1, 2, 4, 5, plus one deliberate break and a rollback.
- **Should:** 3.
- **Could:** 6, 7, 8.

## Not in scope
Infrastructure-as-code, container orchestration, staging environments, dashboards, scaling, polish.

## What I should be able to say afterwards (honestly)
- How a change gets from my laptop to production, and what stops a bad one.
- One thing that broke during deploy, how I found it in the logs, and how I fixed it.
- How I rolled back, and how long it took.
- How I'd know it was down.
- How it behaves when the same request arrives twice.

Call it "my own project", never "production at scale".
