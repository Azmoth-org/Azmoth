# 🐙 The 14 pains of billing for AI agents

- **URL:** https://arnon.dk/the-14-pains-of-billing-ai-agents/
- **Author:** Arnon Shimoni
- **Published:** 2025-07-26T21:51:16+00:00
- **Modified:** 2026-01-23T08:43:10+00:00
- **Type:** post
- **Topics:** ai, billing, pricing
- **Tags:** billing
- **Reading time:** 8 minutes
- **Description:** (Basically, why the octopus grew new tentacles for agentic billing) A while ago, I wrote about the 14 pains of building your own billing system – that was back when billing was “just” complicated. It got mentioned quite a bit around the internet, and ended up #2 on the front page of Hacker News which […]

(Basically, why the octopus grew new tentacles for agentic billing)

A while ago, I wrote about

the 14 pains of building your own billing system

– that was back when billing was “just” complicated.

It got mentioned quite a bit around the internet, and

ended up #2 on the front page of Hacker News

which was nice 😊

Now we’re in the agentic era, and that billing octopus grew some new tentacles just for AI agent billing. Or is it a different octopus? I’m not sure.

Anyways, as octopus go, these are autonomous ones that move without your permission and consume resources we didn’t budget for.

I love the octopus analogy because it touches everything.

I just think they’re neat

If you’ve spent any time with billing systems before, you know that billing systems are

complicated

, and no one wants to think about them. When they work, it’s great and everyone is happy.

And If you thought traditional SaaS billing was hard to build, wait until you try billing AI agents that work 24/7, make their own decisions, and deliver outcomes instead of features.

Yes, this is true. Don’t @ me.

The fundamental assumption of SaaS billing (humans using software predictably) is not relevant anymore.

So, why?

Why does SaaS billing break with AI agents

A reminder:

👉 if you can’t collect revenue legally and correctly, it’ll become your headache and you’ll have more on your plate than you could possibly ever chew 👈

And while SaaS billing worked because it was built around humans:

Humans sit in seats

Humans use features during business hours mostly

Humans make predictable upgrade decisions infrequently

Humans consume resources in measurable ways with some minor exceptions

AI agents break every assumption:

No seats (one customer deploys 50 agents, another deploys 2)

No business hours (agents work 24/7 across time zones)

No predictable usage (an agent might cost $0.10 one day, $50 the next)

No clear feature boundaries (agents execute workflows, not features)

Unlike what some subscription billing vendors are doing, you can’t just add “AI” to your existing pricing page and call it done.

Some vendor, probably

So, in building on the original 14 pains, here are the new complexities that traditional billing systems struggle with – and even more reasons why

you really should not build your own billing system.

1. Date handling becomes temporal chaos

Remember timezones being hard? Try billing an agent that works across 12 timezones simultaneously, making decisions at 3 AM that affect monthly quotas.

When exactly did that “monthly” cycle start?

What happens to credits that expire?

2. Usage metering – but did it work?

AI agents make lots of calls to services downstream – from voice, LLMs, avatar generation, etc.

An agent can sometimes make dozens of API calls to complete one task. Some failed, some succeeded, some were retries.

Which ones count toward the customer’s usage? All of them? None of them? Just the successful ones?

These can’t be treated in isolation anymore.

3. Proration when there are no seats

Customer wants to upgrade their agent’s capabilities mid-month. But there’s no “seat” to prorate.

Do you prorate the the outcome quota? The compute allocation? Credits? Tokens? Just the input tokens or also the reasoning tokens?

4. Invoice formatting for outcomes vs features

Your invoice used to say “5 users × $50 = $250”.

Now what? “47 sales emails generated, 12 meetings booked, 3 deals advanced = $???”.

How do you itemize autonomous work?

5. Customer hierarchy meets agent delegation

Your customer’s subsidiary deploys an agent that works for multiple parent companies.

The agent books meetings for Company A but uses Company B’s compute credits. Who gets billed what?

Are you just going to shift to BYO and let the customer pay for their own credits?

6. Tax handling for services performed by non-humans

Is an AI agent performing work in California subject to California tax?

What if the agent “lives” in AWS Oregon but serves a customer in New York?

Is it a service or a product, or (gasp) a human replacement?

Tax is complicated.

7. Crediting and refunding autonomous failures

Your agent screwed up and sent the wrong email to 500 prospects.

Customer wants a refund. But the agent also successfully booked 12 meetings that same day.

How do you account for autonomous failure, assuming the work was actually done?

8. Complex entitlement workflows for complex agent workflows

Say a customer’s payment fails mid-month after they ran out of credits.

Do you shut down all their agents immediately? Just the expensive ones? What if an agent is mid-workflow on a critical task? Downgrade them to lower models, throttle them?

9. Custom deals when you can’t predict usage

It’s often the case that the enterprise customers want custom contracts.

But neither you nor they know how many meetings their agent will book, how much compute it’ll need, or what success rate it’ll achieve. How do you handle the CPQ for this?

CFOs love predictable pricing, still, for some reason – and I think that’s down to very poor forecasting tooling.

This will change – but only if people push for it to change, like this guy did 👆🏻.

10. Revenue recognition for future outcomes

You bill today for an agent that will work for 30 days. But the “outcome” (meeting attendance, deal closure) happens in month 2.

When do you recognize revenue? When you bill or when outcomes occur?

Do you roll over outcomes?

11. Idempotency in an autonomous world

Your agent retries a failed action.

Your billing system sees it as a duplicate workflow and ignores it. The action succeeds on retry. Customer gets the outcome but isn’t billed.

12. Entitlements are hard for autonomous agents

Customer pauses their subscription while their agent is mid-way through a 5-day outreach sequence. What level of access do they get? Does the agent finish the sequence or stop immediately?

13. Multi-modal cost allocation

Your agent used text processing, image generation, and voice synthesis to complete one task. Each has different cost structures and vendors. How do you allocate costs and set prices for the combined workflow?

14. Outcome-based pricing meets attribution hell

You charge per “qualified meeting booked”, but the agent sent 50 emails and made 13 LinkedIn connections before booking the meeting with one stakeholder eventually.

Which action “caused” the outcome?

The three patterns I see

The same three approaches from my original post still exist, but they’re all more broken now.

👷

Build your own

a

gentic billing

💸

Hybrid agent billing

🪑

Traditional SaaS + agents

What it is:

Build everything from scratch, including agent cost tracking, outcome attribution, and workflow billing

What it is:

Mix of home-grown agent logic with traditional payment/tax providers

What it is:

Force agents into seat-based or traditional usage pricing

The reality:

Full control, but now you’re building distributed systems monitoring, ML cost allocation, and outcome verification on top of traditional billing complexity

The reality:

Better than the other options, but you’re still building the hardest parts (agent attribution, workflow pricing, outcome verification) while integrating with systems that don’t understand agents

The reality:

Convenient until your first customer asks “why am I paying per seat when I have no users?” or “why does my bill spike randomly?”

Who should do this:

Companies with unlimited engineering resources and very specific, niche agent billing needs

Who should do this:

Most companies, if they can find the right mix of tools

Who should do this:

Nobody. This is like using a calculator to run a supermarket

The “force agents into SaaS billing” approach is the new “roll your own auth” of 2025. Lots will try it, and they’ll regret it.

It will be no secret that I think outcomes is the best way for agents. Fight me in the comments.

The bottom line

The original billing complexity hasn’t gone away. We’ve just added a whole new layer of agentic complexity on top.

The new pains fall into a pattern:

autonomy amplifies every existing billing complexity while adding new dimensions of attribution, outcomes, and temporal chaos.

What should you do about it?

Look. Seriously –

the best billing system is the one you don’t have to build yourself.

You need a billing system that understands:

Signals, not just events

Outcomes, not just usage

Agent workflows, not just user sessions

Variable costs, not just fixed pricing

Value creation, not just feature consumption

For AI agents specifically, you need:

Cost tracking across all AI providers

Billing that maps agent activities to business outcomes

Margin protection / entitlements that prevents negative-margin customers from taking root

Value reporting that proves ROI for renewals

Flexible pricing models that evolve with AI cost curves

Don’t build this yourself. It’s even more complex than traditional billing. The same problems are there, but there’s 14 more of them.

That’s why I’m building

Solvimon – an ultra flexible AI monetization and billing engine

– so that you don’t have to.

Welcome to the agentic era. Hope your billing system is ready!

More in my series on billing:

🦑 The 14 pains of building your own billing system

Design your pricing and tools so you can adapt them later

How we built a Cashback system with Stripe

You’re pricing your SaaS wrong but that’s probably OK

You should separate your billing from entitlements

5 things I learned while developing a billing system
