# Design your pricing and tools so you can adapt them later

- **URL:** https://arnon.dk/design-your-pricing-and-tools-so-you-can-adapt-it-later/
- **Author:** Arnon Shimoni
- **Published:** 2023-02-04T05:15:15+00:00
- **Modified:** 2024-01-23T13:03:25+00:00
- **Type:** post
- **Topics:** billing, product management
- **Tags:** billing, entitlements
- **Reading time:** 9 minutes
- **Description:** In this blog post I’ll talk about three pricing architecture concepts that I think are really important in modern billing – designing pricing and packaging to be adaptable. I’ll build upon the experience our billing infrastructure team had at Pleo, which has allowed us to expand to new geographies, currencies, and adapt pricing very rapidly. […]

In this blog post I’ll talk about three pricing architecture concepts that I think are really important in modern billing – designing pricing and packaging to be adaptable.

I’ll build upon the experience our billing infrastructure team had at

Pleo

, which has allowed us to expand to new geographies, currencies, and adapt pricing very rapidly.

Your pricing

will

change

When you build your new product or service, you build it without testing it on the market, and on real customers. At least initially, anyway.

It’s very probable that you will need to change your pricing and feature packaging.

Even pricing you have tried out and works, will have to change.

Consider these four examples of possible impacts on your pricing:

Four examples of things that could impact your pricing and packaging requirements

From left to right:

Your product offering changes over time. You add features, you remove some others, and you figure out which ones your customers want to pay for.

Example

: Netflix adding HD video, and removing DVD rentals.

You may decide to move to new markets, expand to new “verticals” or industries, or even target new types of customers.

Example

: Spotify entering the audiobook market, or entering India.

You decide to move features from one “package” to another.

Example

: Slack moving SSO to be a premium feature.

Your competition changes your market, and changing customers’ perception of how valuable a feature is.

Example

: Google Fi offers a free phone plan.

You could very well be operating in an area that has all of the above affecting your business. Therefore, I believe it’s impossible to outright design an evergreen business model, with pricing and packaging.

Because of these, you

must

build and design pricing to be adaptable and flexible for future changes.

So what should you be considering?

I think it’s mostly down to these three concepts:

Pricing, by design, should be append-only (never change existing prices in-place, only replace)

Use SKUs to maintain different pricing versions

Packaging and features, as well as pricing plans can be added without modifying billing – meaning, you should use entitlements checking

Avoid grandfathering entirely

I will now explain what these concepts mean, again, building on my billing infrastructure team’s experience at Pleo:

1. Pricing should be append-only and versioned

What:

Once used by even a single customer, the price can’t (and shouldn’t) be modified anymore – it is archived. Any changes need a new price with a new SKU.

Why:

Append-only pricing design may seem like an annoying limitation, but it helps you plan better and prevent “versioning” mistakes. (If you use a service like Stripe, your pricing is already append-only!)

Yes, you can still add new prices at any time, but you can’t modify ones that you’ve already used.

Once you’re ready to toy around with new pricing and new variations – you can deprecate and “archive” the old price and create a new price object which becomes the new default.

For your customers: existing customers can retrain their old prices until they are migrated (we’ll talk about grandfathering a bit later), but new customers can’t get the old price, since it was archived and can’t be used anymore.

With append-only pricing, only new customers get new prices. Old customers retain old prices until they are migrated

One way I use to manage new price versions is with a rolling SKU.

Actually, let’s talk about SKUs a bit…

SKUs and versioning

What:

SKUs help you manage your pricing versions, and you can design them to allow for adaptability.

How:

This may not be the dogmatic way of doing SKUs, and I’m sure there’s some SAP guide on how to do these right, but I found that this approach worked for me.

First, you need to know what your specific degrees of freedom are.

An example from Pleo, where I had identified the following attributes:

Countries we operated in (UK, Germany, France, Denmark, …)

Several product types (e.g., SaaS Platform, Financial service fees, implementation professional services, physical credit cards, etc.)

Our SaaS platform had four levels ranging from “Free” tier to “Premium” tier

The SaaS fees had different payment terms (mostly monthly and annually)

Between those four factors, I came up with this structure for a SKU which was both simple and extensible, when our business model changed:

Example anatomy of a SKU, which we used at Pleo

All combined, and with the addition of a

revision

, we started using these SKUs to version our prices.

I usually spaced ‘tiered’ products apart, so that we could, in the future, add products between our free tier (

110

) and our next tier (

120

).

Initially all products and prices ended in ‘

00

‘, but each pricing experiment and update we unleashed into the world increased that number.

Of course, new tiers and product offerings got their own distinct SKU, which could be both composed and de-composed to understand the specifics of that price plan.

Our business model adapted, we changed pricing and packaging, and our SKUs moved along with us.

2. Modify packaging without modifying billing

What:

Entitlements is what we call access to a specific feature. This can be checked separately from “billing” when properly separated.

Instead of asking “

Is customer

A

on

plan='GOLD'

?

“, you’d be asking “

Does customer

A

have access to feature=

(X)

?”.

Diagram showing entitlement checking. Responses in yellow indicate which features a user may have enabled, and which are possible as paid upgrades. Taken from

You should separate your billing from entitlements

Why:

This seemingly semantic difference is actually really important. Feature access is set on a customer-basis, but can still be derived by the pricing plan, the phase of the customer’s lifecycle status (e.g., on a

trial

or in their

evergreen

phase), instead of just the plan type.

I’ve already written about entitlements in a moderately successful blog post called “

You should separate your billing from entitlements

“.

Entitlements are specific features and variations and they change based on your different markets, plan levels, and even sometimes with payment terms.

This concept is core to being able to tweak your prices and change your packaging without having to redeploy and migrate customers’ billing.

It has several major benefits:

You can change packaging without affecting existing customers by creating “feature overlays” for existing customers – even if you move them from old plans to new plans.

Adding and changing plans can be done without having to redeploy code. If done right, it may just be a new database entry in your entitlement service/module.

You can schedule new plans and features ahead of time, and deprecate old features on a schedule too.

You significantly lower the chance of botched feature releases, because customers won’t have access to yet unreleased features.

You create a possibility to trial new features without having to modify billing.

You gain a single source-of-truth for which features are alive for every customer and plan.

Final but most importantly, it allows you to…

3. Avoid grandfathering entirely

What:

Grandfathering is the concept of leaving a customer on an old plan that you don’t offer anymore, while offering new plans to new customers.

Not respecting a customer’s entitlements is often perceived as worse than a price increase or change. Customers may feel like they have been tricked – so some companies resort to grandfathering.

While very common with legacy phone companies, it has fallen out of favour in our more modern SaaS world.

Why:

The reason it’s considered harmful in SaaS billing is that it leaves you with a long tail of plans that you have to keep maintaining, to avoid angering customers.

Crude graph of a long-tail distribution of customers on a price / plan over time. If you don’t proactively migrate them away from those plans, they’ll be effectively grandfathered on them.

However, the operational cost is immense. If a customer is on a grandfathered plan ever wants to upgrade, the logic for how to upgrade can get outdated and may fail entirely if not properly maintained – triggering manual work for you in after-care or even deterring the customer from sticking around.

The concept is therefore:

You should avoid grandfathering plans and you should think about it from day one in your pricing design and tools.

How

: You can always move your customers to new plans, but create entitlement overlays to make sure they get the same level of service.

For example, if you have early adopters who got access to all features for $3 per user – you should be able to:

Migrate them to a new

plan (potentially more expensive and more limited) with a discount (e.g., $10 per user with 70% off)

Override some entitlements

to grant them all their old features and limits (e.g., 30 movies limit, HD quality), while also retaining the new features from the newer plans.

Combining discounts and overrides will enable you to avoid grandfathering customers on old plans, and will ultimately simplify your billing.

Recap

I believe that if you follow those three concepts, your pricing and packaging will remain adaptable to most future requirements.

Again, they are:

Pricing is append-only

Use SKUs to maintain different pricing versions

Use entitlements instead of pricing to check for feature access

Avoid grandfathering

Good luck, and keep experimenting with pricing!
