# 🦑 The 14 pains of building your own billing system

- **URL:** https://arnon.dk/the-14-pains-of-billing/
- **Author:** Arnon Shimoni
- **Published:** 2024-02-19T22:32:58+00:00
- **Modified:** 2026-01-23T08:42:32+00:00
- **Type:** post
- **Topics:** billing, pricing
- **Tags:** billing
- **Reading time:** 8 minutes
- **Description:** Trying to cobble together your own billing system is like wrestling an octopus that's armed with tax codes and invoices instead of tentacles. It's a beast of complexity that can tangle up everything from customer support to compliance. I have 14 points on why it's hard.

Billing and revenue systems are a necessity if you ever plan to monetize your business.

If you’ve spent any time with them, you know that billing systems are

complicated

, and no one wants to think about them. When they work, it’s great and everyone is happy.

I’ve seen them likened to an octopus, and I fully agree. They touch finance, product, experience, customer support, customers, legal, compliance, sales, and sometimes more.

Billing is hard, intertwined, and complicated.

Because it’s so inter-connected, it can go belly-up rather quickly if something breaks. And stuff does break.

Frequently

. (If you have a team that’s maintaining this system and it’s not you, ask them!).

Also, if your system isn’t breaking just yet. Give it some time.

Look, I know you are busy running the business and you already have lots on your plate. You just want to collect some money and move on to more pressing features that actually matter to customers.

But remember:

👉 if you can’t collect revenue legally and correctly, it’ll become your headache and you’ll have more on your plate than you could possibly ever chew 👈

The three patterns

This is not unique to billing systems. It is very common to see one of three patterns:

Home-grown

Full 3rd party system

or a hybrid of a home-grown and 3rd party system

These all have their own benefits and drawbacks, naturally.

Build your own / Home-grown

Hybrid

3rd party

An entirely home-grown solution.

The control is hard to beat. Full control, fully customizable, and you aren’t paying anyone from the outside for fees.

Many think (and this happens to many companies) that building and maintaining your own billing system is the best option for your business.

A mix of home-grown solutions and 3rd parties.

For example, your billing engine is internal, payments are handled by a PSP, and tax compliance by a tax SaaS.

Here, you can control the business logic (e.g., when do you update quantities), but the logic is handled by the 3rd parties.

A turnkey solution that handles everything for you.

All the business logic, payment processing, invoicing, tax compliance, usage, metering – all done by one full-service solution.

This is convenient for companies, but you lose a lot of control and may have to shell out a lot of money to get to this place

It’s very natural, when you just start your company (or you’re taking your first steps with a new product) to build everything by yourself.

You have engineers. You want to keep it very simple.

Or so you think.

Why not?

Because you’re often still thinking like an engineer.

You’re thinking of billing as an engineering issue. You’ll say to yourself

“why can’t we just dump a file of what we need to bill on S3, and have a CRON job pick it up and collect payment?”

.

But you’re wrong. It’s a very big and difficult problem, you just aren’t seeing it yet.

Here is my very high-level description of the things a typical billing team needs to worry about (YMMV):

A typical billing or monetization team has so many responsibilities that it’s hard to grasp even for seasoned professionals.

Everyone knows you don’t do your own security (or date handling). You also shouldn’t do your own billing from scratch.

The best billing system is the one you didn’t have to build entirely yourself!

via

Permit.io

My 14 pains of billing and monetization

Allow me to list

some

of the problems I’ve had with home-grown billing systems, from least complex to most complex (partial list!):

1.

Idempotency

. All requests to do billing, collecting payments need to be unique and idempotent. This will become apparent when you hit API limits and need to retry, or need to spin up more instances of your billing system. Then, you risk double-charging. Luckily crediting/refunding is not a big problem, but this is a problem nonetheless when you scale your infrastructure.

2.

Date handling.

When do you bill? Every 30 days (calendar), or every month (anniversary)? What about leap days, time-zones, etc?

via XKCD: 2687

3.

Proration and “leftovers”

. Do you prorate on upgrade or only downgrade? Refund? Credits? Ignore it? Block it from happening (don’t allow upgrades/downgrades)?

4.

Usage metering.

There are dozens of way to decide how to calculate usage,

and

they can be changed frequently or by customer type

5.

Invoice formatting

. Sounds easy if you’re operating in one country. But when you expand you suddenly realise you have to collect not just sales tax, but also sometimes VAT and sometimes GST and sometimes additional levies (country-dependant) and you now need individual templates for each market.

6.

Complex customer hierarchy

. Customers (especially in B2B) could have subsidiaries and partners that they want to manage their billing relationships. How do you roll-up usage up to the paying entity?

This is often something that you don’t think about at first, but changes when you grow and expand.

Making that even more complex: They could be in different locations, and taxed differently based on their location or where the services are delivered. Then, you are legally required to split the bills/invoices.

These rules can also change every few months

7.

Payment collection and churn prevention

. When do you give up retrying? How do you handle chargebacks (terminate the account, suspend, refund)?

8.

Pausing/resuming

. What level of access do you let customers have when they pause their subscription?

9.

Crediting / refunding

. If you always refund the entire amount it may not be hard, but what about partial mistakes? Would you maybe want to give a “store credit” instead of a refund? Should that credit ever expire?

10.

Tax handling

. You may think different items having different tax rates is complex enough, but these also change frequently if you’re on the global level.

11.

Custom deals

. If you’re PLG-only this isn’t an issue but if you sign contracts, you will very quickly end up with edge cases and special deals that can’t be easily configured with the assumptions you made.

12.

Human error.

Customers are often comprised of humans who have made mistakes, and corrections need to be made. Businesses too are comprised of humans, who can misconfigure their customers and then need to make corrections. Crediting and reissuing invoices is a very time-consuming task.

This is also true when customer’s legal details change (address, VAT ID, etc.)

13.

Selective pricing changes

. Pricing changes often don’t affect all customers. When only new customers are affected, you must keep distinct versions of your pricing points to ensure customers’ agreements are kept.

@j_poli

Should be easy, right!?

#startups

#tech

#developers

#siliconvalley

#venturecapital

♬ original sound – Coding with JP

14.

Revenue recognition and accrued revenue.

I can’t even begin to explain this – but

here’s a 64 page PDF specification of revenue recognition rules according to IFRS-15

. If you understand this – you’re special and please e-mail me, I want to know why.

Bonus points if you also did a custom

ERP integration

🥲.

Why are these hard?

Some things change very regularly, more than you’d expect. Some things you only have to do once and never touch again.

Idempotency is a great example of an engineering issue that, once solved, rarely has to be touched.

However, tax rules change regularly across the world. The more countries you’re in, the more tax laws you have to keep track of.

Customer problems around mistakes is a relatively constant issue, but it increases in size as you grow, requiring more customer support and more manual corrections.

Let me try and put it in a table. It’s entirely subjective, but it should help explain the relationship between how frequently things change (== break), and how impacted they are by scale.

Changes frequently

/ Impacted by scale

🤏

Somewhat impacted by your scale

📈

Highly impacted by your scale

🪨 Doesn’t change

* Idempotency

* Dates

* Pause and resume rules

* Crediting / refunding

* Human errors

🦥

Changes sometimes

* Proration rules

* Customer hierarchies

* Usage calculations

* Payment collection

* Pricing changes

🐇

Changes frequently

* Custom deals

* Revenue Recognition rules

* Tax handling

* Invoice formatting

My subjective assessment of why some topics are more difficult than others

tl;dr:

Billing is

initially

an engineering problem rooted in a very very complex problem space which is really hard to understand even for industry veterans.

What should you do about it?

I said it earlier and I’ll say it again: The best billing system is the one you buy from someone else.

Offload as many problems as you can to someone else. Buy something off-the-shelf. Buy as much as you can.

I can’t stress this enough.

Let the best billing systems like

Solvimon (the best European alternative)

,

Orb

,

Lago

or anyone else manage your billing when you start. 90% of the “Subscription and billing” section in the diagram above can be handled by any of these.

Let the best ERP (that’s the one you already have) handle your RevRec/Accounting (or use what’s built in with something else).

You should only focus on updating the usage / basic customer lifecycle events, the things that are unique to your product.

More in my series on Billing:

Design your pricing and tools so you can adapt them later

How we built a Cashback system with Stripe

You’re pricing your SaaS wrong but that’s probably OK

You should separate your billing from entitlements

5 things I learned while developing a billing system
