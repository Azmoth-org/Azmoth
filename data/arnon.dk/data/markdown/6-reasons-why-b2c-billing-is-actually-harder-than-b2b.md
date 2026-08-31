# 🤔🔍 B2C billing is actually harder than B2B billing

- **URL:** https://arnon.dk/6-reasons-why-b2c-billing-is-actually-harder-than-b2b/
- **Author:** Arnon Shimoni
- **Published:** 2024-11-13T05:03:17+00:00
- **Modified:** 2024-11-13T09:43:39+00:00
- **Type:** post
- **Topics:** billing
- **Tags:** billing
- **Reading time:** 11 minutes
- **Description:** We often neglect to consider how B2C billing at Spotify, Netflix, HelloFresh, ClassPass, and even ChatGPT work. Because it feels like a solved problem it is very often underestimated. Don't build it yourself.

We all love a B2B SaaS ❤️. A few months ago I wrote about

14 reasons why building your own billing system

(mostly for B2B SaaS) is hard. Here are 6 more so that we can round it up to a nice 20!

While we all really do love a B2B, we often neglect to consider how B2Cs like Spotify, Netflix, HelloFresh, ClassPass, and even ChatGPT work.

Because it feels like a solved problem (a recurring monthly fee in exchange for access to a service), we think it may be easier to do, and it is very often underestimated.

I think B2B is quite well understood, and despite

still

being complex 🐙, B2C is even more complicated. Especially if you are successful and have millions of customers.

Let’s understand why, and why we don’t recommend you build your own B2C billing yourself.

1. B2C has way more “levers”

One of the biggest challenges in engineering is designing for adaptability. The most successful companies continually experiment with their pricing strategies and packaging configurations. Without the ability to evolve and iterate on your pricing, you’re not only leaving revenue on the table but also sacrificing profit margins.

If we take a company like Netflix, they probably have over 200 different price-points, and different discounts and coupons and promotions at any given moment. The marketing managers in B2C companies demand the ability to run individual campaigns.

If you’re thinking of developing a billing system based on a static set of requirements or user stories, you’re engaging in short-term thinking. No business wants to be stuck with constraints on their pricing strategies.

Consider this REAL example of how real billing and monetisation levers look like at an established B2C company:

Around 160,000 combinations that need to work and be tested regularly

.

Any change to the model above – either with new payment methods on checkout, new payment terms (“Let’s do weekly subscriptions!”), or new products need to be tested

extensively

.

“But my sales people like freedom also!”

Yes, in B2B, negotiating a contract is much more common than in B2C, where customers are more likely to self-serve into a subscription if it meets their needs.

In B2C common monetization techniques include product bundles, season passes, microtransactions, and DLCs (downloadable content) — all of which are really difficult to get right when building from scratch.

Markets evolve, businesses change, and billing systems need to keep up. While it is equally true for both B2B and B2C businesses, a clear B2C monetization strategy is often more critical both as a key differentiating factor, and customer acquisition lever.

In B2B it is common to create a custom fixed price quote when other stuff doesn’t fit.

“I still want to build it myself”

You should ask yourself what types of pricing experiments can you expect to run in the future…

Which countries are you launching in, and how will you price it regionally?

How will you handle things like promotions, discounts, and special offers?

Will you also offer a B2B-style subscription? What additional complexity does this add?

How will you package your offering? (e.g. “good, better, best”)?

How will you gate features and benefits to their respective subscription tiers?

Which exceptions will you need to account for?

It’s not impossible. Building a system that can adapt to the necessary scenarios does however require an abstract approach. You’re not just building for today but for the next five years of business needs. You’d want to future-proof your platform to accommodate for unknowns in pricing, packaging, and feature gating.

2. Global rollout means global problems

As soon as you step outside of your home country, billing complexities grow exponentially.

Not just because customers are different globally and have different expectations of what expensive is (that part is easy to handle), but also because there is a complicated web of tax laws, regulations, and compliance challenges.

These

will

severely hinder your progress if not addressed early on.

While a $9.99 monthly subscription in the U.S. excludes sales tax, the same price point in the EU would need to include VAT (or GST, or a variety of other taxes you will be liable for). Handling VAT, GST, and other regional taxes can become a monumental headache if you don’t plan for it. Not to mention the variation in how taxes are calculated, reported, and remitted across jurisdictions.

Who doesn’t love tax laws

Did you know that in some countries you are not allowed to automatically renew a subscription? Yeah, it does not always work the same way globally. Some countries and US states prohibit renewing a yearly subscription without an explicit opt-in from the customer at least 30 days in advance.

So you gotta handle that also…

Additional complexities

Differing tax structures for physical vs. digital goods and services

Real-time tax rate updates

Regulatory compliance and financial reporting requirements

A billing system needs to account for these variances seamlessly. At the same time, certain regions are also rolling out new digital tax regulations, ,like the EU’s VAT for digital goods. If your system lacks the flexibility to handle tax treatments by country, you’re guaranteed to run into compliance issues quickly.

3. Payment Methods and PSP integration

I love payments. They seem so easy from the user perspective, but don’t let that fool you.  Payments is at the core of your billing system, and integrating with one

OR MORE

Payment Service Provider (PSP) is one of the most crucial aspects of smooth transactions. And you want to get paid, right?

In B2B you don’t have to worry about that. Worst case you send an invoice and receive a bank transfer. Cool.

You can always just invoice in B2B. Can’t really do that in B2C.

Can’t really do that in a B2C. And this is more than just enabling credit card payments.

Customer preferences change not only depending on region, but also between social classes, and also over time.

In Europe, local payment methods like SEPA and iDeal are common, as is Klarna.

In the US, credit cards reign supreme but wallets are starting to become more popular.

Companies in Asia prefer e-wallets like WeChat Pay, Alipay, and Line Pay — as well as a variety of other methods like paying at a Konbini (payments made at a kiosk, often at convenience stores).

B2C often has a much higher VOLUME of transactions compared to most B2B businesses, even when the transaction value (ATV) is lower.

Do you know how to handle 5 million “renewals” on a single day?

What happens if your PSP drops some payments and you have to retry them? This can amplify issues related to Idempotency (ensuring transactions are only processed once), as well as low volume transactions (like upgrades, overage charges, pay-per-use).

Coupled with the different payment methods you’d want to offer, this becomes quite a big challenge!

Don’t underestimate how difficult it is to write your own orchestrator for payment gateways and their associated fees and reconciliation processes.

To stay competitive globally, you need deep PSP integrations that allow you to:

Handle local payment methods:

Every region has different preferences, and you need to cater to all of them.

Card updates and retries:

How will you handle automatic card updates? Will your system retry failed payments and manage dunning campaigns for expired or declined cards? Features like “shopper-initiated” card updates and confirmation of payee are crucial for keeping churn rates low.

Chargebacks and refunds:

The ability to handle chargebacks and refunds is essential in a billing system in order to mitigate and resolve disputes between your business and customers.

Fraud management:

Can your billing system detect and handle fraud? A weak system could expose you to serious financial losses.

4. Failures, dunning, retrying – also harder with B2C

Payment failures are inevitable. Whether due to insufficient funds, expired cards, or network errors — how you handle retries can directly impact your churn rate. A good billing system doesn’t just stop at a failed transaction.

It automates the process of retrying the payment and, if unsuccessful, initiating dunning features that nudge customers to update their payment information.

Customers globally get paid on different days. In Sweden, you get paid by the 25th. In Denmark, you get paid by the last day of the month. In the US, many get paid every two weeks.

The dunning strategy (fancy word for retrying the payment) has to take that into account.

The key is taking a multi-step approach to retries, which can be hard to get right when you build it yourself.

Consider the cost of a retry, best time to do a retry, number of retries, and how this can differ per country and payment instrument. Simple dunning strategies are able to recover 50%, but smart dunning can recover up to 70% of failed payments.

This meme

stolen from Tesorio

Also, different payment methods across the world behave differently, and what may seem trivial for your own market gets exponentially more complex as your business starts accepting more payment methods.

Did you know that the card networks can also penalise you for doing this wrong? Yep, gotta think about that also!

5. Keeping Finance and Compliance Happy

Most of all, your billing system needs to keep your finance department happy. That means providing detailed, accurate, and compliant reporting; integrating with accounting systems; managing deferred revenue; handling refunds correctly; and being audit-ready at all times.

If your billing system isn’t built with this in mind, it can put your finance teams (and your business) in a tough spot.

Considerations for finance integration:

Can your system generate financial reports in compliance with local regulations?

Does it support revenue recognition rules, such as ASC 606 or IFRS 15?

How does it manage refunds and chargebacks?

Without real-time financial insights, you’ll be flying blind, making strategic decisions based on incomplete or outdated data. A well-structured billing system will integrate seamlessly with financial systems, ensuring smooth cash flow management and accurate forecasting.

We also guarantee that if you can’t automatically reconcile the fees you pay for payment processing with the revenue, the finance team will not be happy.

6. Mobile first is the norm, without a sales rep involved and helping.

Customers in most of the world expect a mobile-first approach when buying or subscribing. The share of customers using computers to subscribe keeps getting smaller as the younger generation becomes prevalent.

Unlike a business which will have people using their laptops, and usually go through some purchasing process – the younger generation primarily interacts with services through their smartphones and operates a lot more on feeling.

Some things to consider:

Your checkout and payment process is smooth and intuitive on smaller screens

Mobile wallets are king – you need to support popular mobile payment methods like Apple Pay, Google Pay, Samsung Pay, Line Pay, Kakao Pay, etc.

App Store vs. Direct Online Offering – App stores (like Apple’s App Store or Google Play) offer a familiar, trusted environment for users, but often charge quite a hefty fee.

You want to offer customers the ability to subscribe through them, but it comes at the cost of limited control on your product offering if you don’t structure it well.

In B2C, adopting a mobile-first approach is a requirement which B2B can usually live without.

OK so what am I going to do?

Listen, it’s not rocket science. Yes, building your own billing system isn’t just a technical challenge — it’s a business-critical decision that can have wide-reaching impacts on flexibility, compliance, and customer retention.

The problem space is huge, hiding complexities that are often underestimated by both engineers and operations. You can avoid the common pitfalls with the right foresight and planning.

The good news is that you don’t have to build your own B2C billing system.

I have consulted many companies recently, and I end up steering them to platforms like

Solvimon

,

Paddle

,

Recurly

, and Stripe Billing. They offer solutions that cover most if not all of the billing challenges above — while PSPs like

Adyen

and

Stripe

offer integrated, mobile-first checkout experiences that support the most popular mobile payment methods.

I get it. I’m an engineer/product person… It’s tempting to build a system tailored specifically to your immediate needs.

Remember that billing systems must be flexible enough to evolve as your business grows and changes, and you may find your time and resources are better allocated towards your core product and features.

This article was written by Arnon Shimoni and Kim Verkooij

More in my series on Billing:

🦑 The 14 pains of building your own billing system

Design your pricing and tools so you can adapt them later

How we built a Cashback system with Stripe

You’re pricing your SaaS wrong but that’s probably OK

You should separate your billing from entitlements

5 things I learned while developing a billing system
