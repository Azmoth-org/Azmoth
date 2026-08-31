# Operational debt is worse than tech debt

- **URL:** https://arnon.dk/operational-debt-is-worse-than-tech-debt/
- **Author:** Arnon Shimoni
- **Published:** 2025-11-17T21:31:45+00:00
- **Modified:** 2025-11-17T21:31:48+00:00
- **Type:** post
- **Topics:** billing
- **Reading time:** 3 minutes
- **Description:** I’ve touched billing systems inside several companies now, and the same pattern shows up every time: the hard part of migrating off seats isn’t the software, it’s the operational debt baked into the business. This is why billing system migrations take at least 8-10 months. You start (well, engineers start) by thinking a pricing change […]

I’ve touched billing systems inside several companies now, and the same pattern shows up every time: the hard part of migrating off seats isn’t the software, it’s the operational debt baked into the business.

This is why billing system migrations take at least 8-10 months.

You start (well, engineers start) by thinking a pricing change means touching code. A bit of refactoring, maybe some new

entitlements

logic, update the pricing page, ship.

That’s the easy part. That’s the part we think we want to solve, because it looks like an engineering problem.

The real explosion happens around that.

Seat pricing has become operational debt

Seats made sense when software mapped cleanly to people. I

recently wrote about where I think seat pricing it’s going (mostly, away)

.

Part of that is because companies grow faster than their contract language. Our customers’ footprints evolve – and then we begin adding features and stuff but we hack around the model. If you’ve ever been in SaaS you know sales closes “just a one-time exception” – and the CRO approves it. And then one more, and then another – and the original seat definition sprouts tentacles in billing, discounting, procurement, renewals, usage rollups, and RevOps workflows.

If you’ve followed my

🐙 billing analogy

before, this is where the octopus crawls out from under the coconut. Moving away from seat-based pricing becomes an excavation project, digging into all of the business processes – not a database migration. You need to unwind years of accumulated assumptions across the entire revenue engine.

Software is clean. Contracts are not.

You can rewrite a service in a weekend if you’re motivated (or panicked I guess). You can’t really rewrite the pricing logic across 800 customers with custom terms in a weekend or even a quarter, it’s often not even documented. Anyone who has worked with deal desks or RevOps knows this already and is nodding furiously.

Contracts calcify, exceptions multiply, customers get grandfathered and put on “legacy” with a bunch of workarounds (including entitlement workarounds) –  and then every renewal becomes a fossil exhibit of all your past business decisions.

Your legacy business decisions, probably

Then later, your product evolves with more features. AI, god forbid. But also new integrations. So you add consumption pricing, and suddenly the seat model starts bending. Then bending more.

And then it snaps.

Tech debt is local. Operational debt is systemic.

Tech debt is easy, and probably honest. It lives in code you can inspect. It’s usually local to a team or two. You can test it!

Worst case, you spend a weekend screaming at Claude Code: “fix pls”

Operational debt is not local. It’s systemic. It’s invisible until it explodes. And it can’t be tested easily.

All those hundreds of small decisions across finance, sales, support, product, legal, and customer expectations are all connected in ways nobody documented.

So yes, tech debt slows you down.

But operational debt traps you.

Unwinding it feels worse.
