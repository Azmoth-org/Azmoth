# 5 things I learned while developing a billing system

- **URL:** https://arnon.dk/5-things-i-learned-developing-billing-system/
- **Author:** Arnon Shimoni
- **Published:** 2021-04-05T16:56:15+00:00
- **Modified:** 2022-04-04T13:55:25+00:00
- **Type:** post
- **Topics:** billing, product management
- **Tags:** billing, product management
- **Reading time:** 11 minutes
- **Description:** Half a year ago, I joined Pleo, a FinTech startup with around 15,000 customers (we’re always hiring at Pleo!). I joined to take on and further develop the billing infrastructure. When I joined, I was actually a bit concerned about the narrowness of the new role and the new team. I mean, really… How much […]

Half a year ago, I joined Pleo, a FinTech startup with around 15,000 customers (

we’re always hiring at Pleo

!)

. I joined to take on and further develop the billing infrastructure.

When I joined, I was actually a bit concerned about the narrowness of the new role and the new team. I mean, really… How much depth could there be in billing? Would we not run out of things to do after 3-4 months?

A customer joins, pays for their subscription monthly, and that’s it… Right?

……. right?

Well, yes but also actually no. This covers only the most basic scenario, and there are TONS of edge cases and gotchas.

Figuring out these edge cases one-by-one wasn’t great. I wish someone had created a short guide of what I needed to know.  So here it is! My guide. If you’re thinking of building (or even just using) a billing system – pay close attention.

Money isn’t always decimal

A common wisdom in database design is “never using floating-point numbers for money”

*

. Some recommend using the

MONEY

datatype, while others tell you to use

DECIMAL

.

For billing systems – both of these are

sometimes

wrong. Sure, yeah, in the US and most of Europe, money is decimal.

That’s certainly not the case in Japan – you can’t charge 2500.50 JP¥. But you don’t need to go all the way to Japan. Iceland doesn’t have subdivisions for their currency either. On the contrary, the Iraqi Dinar has three decimal points in the subdivision.

Technically, you could argue that integers are decimal too, but they can break your system in ways you aren’t considering. So,

when you’re building a billing system, you have to build it extensible enough to handle events in these countries even if they’re not in your current focus.

Store money including the smallest possible subdivisions you will use.

For example, in most situations:

$100 US may be stored as

10000

2500 JP

¥ stored as

2500

2500 ISK stored as

2500

100 Iraqi Dinars as

100000

Here is an excerpt for currencies with no subdivision (column D)

Code

Num

D

Currency

Locations listed for this currency

BIF

108

0

Burundian franc

Burundi

CLP

152

0

Chilean peso

Chile

DJF

262

0

Djiboutian franc

Djibouti

GNF

324

0

Guinean franc

Guinea

ISK

352

0

Icelandic króna

Iceland

JPY

392

0

Japanese yen

Japan

KMF

174

0

Comoro franc

Comoros

KRW

410

0

South Korean won

South Korea

PYG

600

0

Paraguayan guaraní

Paraguay

RWF

646

0

Rwandan franc

Rwanda

UGX

800

0

Ugandan shilling

Uganda

VND

704

0

Vietnamese đồng

Vietnam

A full list of currencies and their subdivisions is available as part of the

ISO 4217 standard, some of which is found on Wikipedia

.

*

If you’re doing risk calculations or trading in penny stocks – sure, keep it floating point

You can’t cancel or void invoices once created

At least not in most of Europe, anyway. In the US, it’s common practice to void unpaid invoices. However, that’s simply not legal in many EU countries. This is a huge headache if you’ve made a mistake!

This is “standard accounting” stuff, but it sometimes hurts to find out about it because mistakes

do

happen. Once created, if you need to cancel an invoice you can really only do one thing: create a credit note for the full amount.

What is a credit note? Think of a credit note as a reverse invoice.

Credit notes are their own unique type of commercial document

, like a reverse invoice. Just like invoices, they have their own number.

So, a credit note is a document that we can use to mark the original invoice as “paid”, even if no money has changed hands.

Credit notes are also useful for changing the total that a customer needs to pay for. Say you invoice a customer for 20 users at £10, but 5 of those users were inactive and should be cancelled. The original invoice for £200 can be credited for £50 (5 × 10), resulting in a £150 balance to be paid.

Not all billing systems are compliant

When you enter a new region, it takes a lot more than just pricing your product and service. You have to make sure you’re compliant with the various rules and regulations – which could be more subtle than you imagine.

Many companies buy services from third party SaaS products, and we often assume that they comply with all necessary rules.

I discovered that isn’t always the case (the onus is on us to verify, of course)

Two examples I came across:

In the EU, the vendor has to make sure that the customer’s VAT number (if used) is correct

before every sale

.

For example,

Stripe only performs the VAT check once

when the VAT is set up. It doesn’t perform any subsequent checks and doesn’t match the customer details.

Some other services don’t do this at all, so make sure you’re compliant!

An

EU VAT invoice has to include specific information

about your own company’s VAT IDs. However, many invoice generators (including Stripe’s until very recently), don’t even include a way to include VAT information.

You may have to find a way to hack your tax details in, using the address field. Either way, it’s up to you to ensure you are compliant!

What happens when a user changes plans?

I thought that signing up a company is easy. They sign up, and after a short trial they use the product as paying customers (“evergreen”), all is great!

The ideal company starts using the product and doesn’t change anything throughout their lifecycle (until they churn)

Like many other companies, we also offer several different levels of service. However, we also charge one month up-front for usage. So, if a customer upgrades or downgrades, we need to change their plan at some point in the future.

A plan change from one to another can happen at a future date, but the customer may want the upgraded service level immediately.

This feels fine, until you start considering some situations

What if they want to get the upgraded service level immediately?

In that case, we can… upgrade their plan but not charge them. This means you need to separate your billing engine from the entitlement engine which dictates the service level!

You can also charge immediately up-front, but what about proration

What if they want to start paying for the new plan immediately too?

(This is way more common than you’d think)

We can upgrade them immediately! But, then do we charge just the difference or do we credit the entire month and re-charge with a new service?

Oh no, we’ve stumbled across the dreaded proration (

Chargebee has a good primer on proration

), which results in very difficult to comprehend invoices for you, customer support, as well as the customer.

A fairly trivial example. Sometimes there’ll be dozens of invoice item lines. Ouch!

Actually, we also want to extend their trial a little bit, so that they can get more grace period in getting set-up

.

This one is actually not that hard…

But sometimes they only remember that they need this after they’ve started the evergreen phase.

This is a nightmare, but you may also need to credit some invoices!

There are probably a dozen more variations on company lifecycles. While these may not happen every time, they will happen when you reach even just a couple hundred customers. Plan ahead for how you’ll be handling these cases!

What about enforcing against edge cases?

Customers aren’t companies. They’re people. And different people have different needs.

Unless you work in a very strict environment, you’ll have to consider how hard you want to enforce your rules.

Here are some minor examples that have come up:

We launch a discount for UK customers only.

Sure, but what about a UK customer who has a sub-company in Germany? Are they also included in this discount? (the answer was yes!)

We launched a campaign during which everyone who signed up got to use the product for free until April 1st, 2021. This was applicable to all companies, even with a multi-year contract.

However, after signing the contract, several companies wanted to pay regardless.

Some companies wanted to pay up-front at the end of 2020 for 2021, because they had a leftover budget which couldn’t be used in 2021.

Our system wasn’t designed to support upfront payment ahead of time.

Whatever limitations you plan for, plan for how to bypass them too. This

will

happen.

In my eyes, it is best to support the business and win customers over, rather than be strict.

It’s never that simple

No matter how easy or simple a problem area looks at first, there’s always a lot of depth, and a ton of questions that need answering.

I’ve learned to appreciate that billing systems are hard to build, hard to design, and hard to get working for you if you deviate from “the standard” even by a tiny bit. However, investing in getting it right leads to happy customers, happy sales and support reps, and a happy finance department!

While those were the top 5 things I wish I knew before I started working on a billing system, they are by no means exhaustive.

You can learn a lot by figuring out how and why big billing systems were designed the way they were (

Stripe Blog: Online Payment Solutions Blog

,

Billing Archives – Chargebee’s SaaS Dispatch

,

Moonpig: a billing system that doesn’t suck

, etc.)

What’s next?

If you’d like to read more about how to “hack” around Stripe and your current system’s limitations – read about

why you should separate your billing from entitlements – and how to design a modern SaaS billing stack

.

[

HackerNews discourse here

]
