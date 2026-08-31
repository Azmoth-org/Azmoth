# How we built a Cashback system with Stripe

- **URL:** https://arnon.dk/how-we-built-a-cashback-system-with-stripe/
- **Author:** Arnon Shimoni
- **Published:** 2022-12-11T16:00:13+00:00
- **Modified:** 2022-12-11T16:12:25+00:00
- **Type:** post
- **Topics:** billing
- **Tags:** billing, cashback, monetization
- **Reading time:** 8 minutes
- **Description:** Recently, at Pleo, we built a cashback system that uses our internal payments infrastructure, as well as Stripe. So while there are other components at play to actually move the money around, Stripe is what drives the cashback events for the most part. Yeah, it’s a bit of a stretch, but it is doable! I’m […]

Recently, at Pleo, we built a cashback system that uses our internal payments infrastructure, as well as Stripe.

So while there

are

other components at play to actually move the money around, Stripe is what drives the cashback events for the most part. Yeah, it’s a bit of a stretch, but it is doable!

I’m going to walk you through what cashback is, how it differs from discounts (or credits), and how we built it. But first, a disclaimer

I don’t really like cashback

Cashback is confusing, and I don’t like it very much.

My intuition is that in the “B2B” world, larger businesses prefer having consistent invoices and payments, and therefore might prefer a higher but consistent, instead of having to bookkeep and deal with a cashback event.

However, I’m not one to argue with results. Our research shows that a lot of smaller customers do really like cashback and consider it to be a competitive advantage.

Our commercial teams started talking about it at some point in early 2022, and so, in May 2022, we collected our entire team for a 3 day hackathon in an airbnb in Crete, and built a full cashback solution.

Pleo’s revenue infrastructure teams (

Team Loki

and

Team Hela

) watching a demo of the cashback solution, built over 3 days, in a team offsite

The MVP went live in July 2022, and the full solution rolled out to the rest of Pleo’s customers in September.

What is cashback?

Cashback is probably one of the most popular ways to incentivise customers to use your product more. It also increases loyalty and therefore the customer’s lifetime value.

Cashback was pioneered by Discover Card back in 1986. It’s kind of similar to rewards points, but cashback is, as it is implied, actual money given back.

At Pleo, customers use their Pleo card to buy stuff for work. Pleo wanted to give 1% or 0.5% of a company’s spend during a month, as cashback. So, if a company spends €1500 during a month, they could earn €15 back at the end of that month.

Cashback is effectively therefore a “refund”

– a percentage of a sum of spent purchases directly deposited back to the company’s account.

For a customer, it’s probably more psychological than anything else. Customers tend to forget about a discount that they got, whereas cashback, given every month, reminds them of the benefit.

For you, a business offering it, it’s going to be a bit different:

Why cashback and not a discount?

This question is kinda tricky, because it has a lot to do with accounting practices and your revenue recognition as the provider of the services!

Typically, a discount involves changing the cost of the goods or services for your accounting. Cashback on the other hand, does not change the price of the goods or services – it is seen as a “cash bonus”.

Put simply, a discount reduces your company’s recognized revenue.

Let’s look at a simple example:

Accounting for a discount vs. cashback

Discount

You price your service or product at €100.

Your recognized revenue would be €100 undiscounted.

You give a 10% discount. The €10 discount reduces the overall price.

Your MRR is reduced to €90.

Your ARR over a year is €1080.

Cashback

You price the product or service at €100.

Your recognized revenue would be €100, and no discount applies.

You issue 10% cashback.

The €10 in cashback is recognized as a sales expense – not a reduction in revenue.

Your MRR remains at €100.

Your ARR over a year is €1200.

If you want to learn more about accounting for these things (why?), you may want to read up on IFRS 15 or ASC 606.

Understanding how cashback is paid out at Pleo

Because cashback isn’t a discount, we pay it out separately, as a separate transaction. That’s important for how we design the system subsequently.

Because it’s a type of benefit, we should first make sure our customers sign up for this. Some may not want it (it may not even be legal for them to accept it!).

The basic flow looks like this:

A rough outline of how cashback should work

Upon selecting a plan, customers are given the choice of a cashback or non-cashback plans. Selecting a cashback-eligible plan would add a special item to their subscription.

Let’s talk about that for a second, actually!

Storing the cashback items on the invoice itself

We could, of course, maintain a list of cashback-eligible companies in our own database. For example, if you read my previous post about

entitlements

, you would think this is a great candidate for adding a cashback entitlement.

And you’d be right in some scenarios – but this isn’t an actual feature or change in behaviour in the application, only in our “billing” application. Because of that, we thought that we should store it in Stripe and activate the cashback only on invoices that have it.

With that in mind, we can create a product and price combination in Stripe, that will not only serve as a reminder to our customers that they are eligible for cashback, but also let us store the details on an immutable invoice. Win-win!

I created a “free” product, with all the metadata we need down-the-line, like this:

The cashback eligibility price item in Stripe

So, once a subscription with this price is created, and the invoice is finalized, we can decide to give cashback.

Processing cashback events

Once we have customers with cashback items on their subscription, the rest is actually pretty simple.

Since we rely on Stripe’s scheduling and processing, it only requires that we listen to the events (via a signed webhook), and tell the payment gateway what to do.

So, we built a cashback service that can calculate how much cashback to give, and instruct the payment gateways to perform the money movement. With those in place, effectively, we have just four steps:

Listen in on invoice finalization (Stripe handles this) with a signed webhook.

The invoice contains the objects telling us about cashback percentages through the special price object.

The cashback microservice calculates the appropriate cashback (e.g., “give 0.1% from the total spend incurred”)

Request the money be paid out from the payment gateway

Send a receipt to the customer once the payment gateway confirms the payment has succeeded

Using Stripe to drive cashback events with a cashback microservice

That all looks fairly straight forward, but unfortunately it’s just the tip of the iceberg.

Where are the complexities with cashback?

Cashback presents a ton of complexities, primarily in ‘after-care’, but also in non-standard billing situations.

Basically, the system above is an “MVP” which we expanded on. We solved all situations desrcrbied below, but I’m not sure if anyone finds those too interesting.

I’ll describe them, and if there’s interest I may write a follow-up post.

Here are the four primary “complex” or edge-case scenarios:

Non-monthly payment terms

The system described above doesn’t handle “yearly pre-payments”. It only deals with monthly payments, because those are the triggers that give out cashback payments.

When a customer wishes to pay upfront for an entire, the described system will not issue cashback monthly because there isn’t a monthly invoice.

Speaking of which:

Predicting how much money needs to be set aside for cashback

Since cashback is not the same as a discount, it often needs to be accounted for separately, form a different cost center.

Operational teams need to ensure you have enough money to pay cashback as guaranteed to customers. That requires good predictability on how much money needs to be set aside to perform these payments.

Predicting this can be difficult when customers have different payment terms and different usage patterns throughout their periods (think monthly, quarterly, yearly, etc.)

Taking intra-period consumption into account

Typically when a customer, paying yearly, adds new products or services during a period, you would issue a new invoice for those added services.

Those invoices should also trigger cashback payments, but they would effectively change the “cap” for the yearly period being considered.

Credits and downward adjustments

The system described doesn’t handle “credits” at all.

Often, customers change their minds, change their needs – resulting in an adjustment to their original billing terms or products.

The system described above doesn’t take into account any refunding or adjustments of cashback payments after-the-fact.

To summarize

Cashback is a neat mechanism to reward customers.

However – this is not an easy problem to solve. There is no off-the-shelf solution for everything.

You

can

reuse (and abuse?) components you already have in your billing infrastructure like Stripe or Chargebee to maintain a big chunk of what cashback needs to do.

Still, there are lots of complexities around the edges which you should take into consideration before designing your own solution for issuing cashback rewards to your customers.
