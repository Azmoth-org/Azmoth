# How airlines use your personal data to reduce delays – and why you should let them have it

- **URL:** https://arnon.dk/airlines-use-personal-data-to-reduce-delays/
- **Author:** Arnon Shimoni
- **Published:** 2019-07-28T20:36:41+00:00
- **Modified:** 2020-11-19T10:02:28+00:00
- **Type:** post
- **Topics:** Analytics
- **Tags:** airlines, analytics, big data analytics, BTS, delays, flights, sqream-db
- **Reading time:** 9 minutes
- **Description:** Hundreds of articles have been written about how airlines track customers to upsell them, offer upgrades, personalize offers, increase loyalty, and even improve baggage tracking. However, one of the most interesting fields of airline operations is adapting to irregular operations – meaning using a combination of customer profiles, weather, route information, airport performance and more to plan, predict, and optimize operations. Can big data help reduce delays?

I love flying. I’m a huge airplane nerd. I always try to plan my flights to earn me the most miles, for the least amount of money. Sometimes, these flights will take me through some weird connections. I don’t mind a layover that’s not too short, but not too long either.

However, many times, even a relatively long layover can completely ruin my travel plans if any of my flights get delayed.

Very few industries have transitioned to using data as
effectively as airlines have. Two decades ago, legacy carriers operated mostly
on intuition, but today most airlines process terabytes of data every day to
keep operations running smoothly in the ground and in the air.

Hundreds of articles have been written about how airlines
track customers to upsell them, offer upgrades, personalize offers, increase
loyalty, and even improve baggage tracking. However, one of the most interesting
fields of airline operations is adapting to irregular operations – meaning
using a combination of customer profiles, weather, route information, airport
performance and more to plan, predict, and optimize operations.

Can big data help reduce delays? We must first understand why and where delays happen.

Understanding why delays happen

Getting planes dispatched on time is hard. There are hundreds of variables and people involved in getting a plane up in the air, where it can make money.

There’s a bit of optimization required from airports and airlines. The airport wants gate utilization to be as high as possible, leaving no “free” gates, as that doesn’t make them money.

The airline wants to use the gate for as little time as possible, because a plane sitting at the gate is actively losing money with every wasted minute.

The time that it takes to get people and cargo off an incoming flight, then prepare the aircraft for the next flight and then up in the air is called a turnaround. With long-distance flights, the turnaround time for a flight can be quite long, but for low-cost carriers, and especially ultra-low-cost carriers (ULCCs), the turnaround time could be as little as 25 minutes.

Behind the scenes of an aircraft turnaround (Courtesy: Adelaide Airport Youtube)

An aircraft usually arrives, taxis to the gate. At the gate, the tricky part starts: Getting people off the aircraft, servicing the aircraft (refuel, restock the catering, clean), boarding new people onto the aircraft, loading their luggage, and finally closing the flight. Then, the aircraft can finally taxi to the runway and take off.

Flight turnarounds are tricky

It’s at the gate that most delays occur, and this is where the airline has the most control. According to the Bureau of Transportation Statistics (BTS), most flight delays are caused by:

[1]

Maintenance

Crew changes (either full or partial)

Checked baggage loading

High load rate (full flights)

Late arriving feeder flights

Cleaning

Fueling

It should be abundantly clear by now that if airlines could predict delay and reduce the aircraft turnaround process, they could reduce delays significantly by responding correctly.

Over 26 million delayed minutes in 2018 alone

In the rest of this blog post, I’ll discuss the data as provided by BTS.gov. This is by far the most complete and comprehensive set of airline performance data we have available publicly. Unfortunately, it is US-only. However, as many airlines operate very similarly around the world, we can assume some of our insights are relevant to the rest of the world too.

Even though delays due to security and weather are mostly down year-over-year, delays due to late arriving aircraft and other carrier related delays are up year-over-year, and could reach up to 45% delay due to late arriving aircraft and 35% due to delays at the gate by 2021. Also, surprisingly only 35-40% of delays are caused by weather.

These delays have a knock-on effect, with flights later in the day being affected more severely (that’s precisely why my colleagues at SQream and I prefer early morning flights).

In the US alone, air carrier delays resulted in 26,316,981 delayed minutes in 2018. That’s over 50 years of time wasted for 373,477 flight operations in just one year!

[2]

To put that number into perspective, if we assume an average of about 80 people per flight, at 70-minute average delay, we’re talking over 2 million wasted minutes, or 3,730 years –

an equivalent of over 53 average human lifetimes

every year due to carrier delays in the US alone!

Carrier delays wasted 53 lifetimes in 2018 alone. Source:

BTS.gov

, Analysis with

SQream DB

What can you do to avoid delays as a passenger?

It’s worth knowing which airports and times to avoid. By connecting a tool like Excel and Tableau to

SQream DB

with BTS’ on-time data in it, we can look at which US airports were the worst offenders in 2018 across several months, and even drill down to specific carriers.

The flight delay data is summarized below:

Carrier delays for 2018 – Analysis through Excel and SQream DB. Using a heatmap and some color, it’s easy to see why we avoid Dallas and Chicago for connections, while Newark and San Francisco are usually still OK. As mentioned, we also avoid short connecting flights in the afternoon and evening, as those are at the receiving end of the ‘knock-on’ effect of flight delays.

A longer term analysis over the entire 190 million row dataset, dating back to 1987 shows that delays gets progressively worse throughout the day, culminating at 30 minute average delays for flights planned to land at 4PM. Avoid those as much as possible, and plan for early morning flights if you can!

A Tableau dashboard connected to SQream DB. An analysis of ~190M records showed that flights arriving at 4PM were significantly more likely to be late.

What can airlines do to reduce delays?

Airlines have been spending a lot of effort in analyzing big
data to streamline performance. Some airlines and aircraft manufacturers have
installed smart maintenance systems that help predict failures and part
replacement.

One example is

Airbus’
Skywise

initiative, in which over 60 airlines share data with Airbus to increase
accuracy and predictability. With the Skywise system, data from different part
manufacturers, airlines, airport, and suppliers are pooled together, which in
turn provides predictive maintenance data. Skywise has already resulted in 35
million proactive maintenance actions on over 5,000 aircraft in the connected
fleet.

Connecting the fleet together is facilitated by a special system called the Flight Operations and Maintenance Exchanger (FOMAX) that captures 20,000 aircraft parameters in real-time. The data analysis tools let airlines anticipate tools and parts availability close to the aircraft’s current and next airport. By knowing when a part needs to be replaced, the airline can ensure the aircraft is either serviced in-line or taken out of service before the failure occurs and substitute another aircraft in its place. This improves fleet utilization and reducing operational interruptions – reducing delays.

Airbus Skywise. (Source:

Airbus

)

Collecting data from sensors and machines is an incredible
step forward in reducing delays, but it’s missing one key aspect, and the most
variable of airline operations – people.

Know your flyers – anticipate turnaround time

While some airlines have integrated a variety of systems, most do not know their customers well enough to predict delays in turnarounds accurately. By correlating a few key parameters, airlines can predict the turnaround times better.

Correlating parameters like load factors, special needs, crew changes, age of flyers, their frequent flier statuses and length of stay can help airlines predict turnaround times

Models such as these for predicting turnaround time are already somewhat integrated with Departure Control Systems (DCS), and even used in ground staff planning systems. The airline already knows how many passengers need to transfer from one flight to the next. By calculating the percentage of business and frequent fliers, perhaps those even travelling without bags, the airline ops can predict the chance of completing the turnaround in the maximum allocated time.

Acting on the models

Leveraging and responding to identified high-risk turnarounds can happen weeks, days, or even during the turnaround.

Ground operations can plan for longer turnaround times, and even position incoming feeder flights closer to the next departing flight, to reduce the time it’d take passengers to navigate the airport on short connections.

The airline can text or send push notifications to flyers phones with tips for making the connection as fast as possible. At the airport, strategically deployed ground staff can instruct passengers and provide information about connecting gates and processes. Airlines can even display this information in in-flight entertainment systems, tailored to each flyer’s seat.

Just recently, United announced their

ConnectionSaver program

, which does just that. Not only does United offer personalized text messages to help customers reach their connection, they may also delay flights to ensure more passengers make their connection.Airlines can also offer to passengers to skip the checked bag with improved carry-on allowance that is tailored to the customer’s profile.

Why I think you should give accurate information to improve on-time
performance

The situation I just described is an actual analytics solution solving a real problem in commercial aviation operations. Most airlines already implement some form of analytics, with more joining every year. However, analytics can only be reliable as the quality of the raw data it relies on. To that extent, by providing the airline with useful, non-intrusive data, the airline can improve flight schedules, properly plan turnaround times, and get you in the air quicker and on-time.

Airlines frequently send out surveys and feedback forms, asking about the nature of the next trip, with an attempt to profile the passengers. Passengers who are already part of the airline’s loyalty programs have even more opportunities of ‘donating’ data to the airline, by explicitly selecting meal choices or by implicitly letting the airline track travel habits.

What about the risks?

I think there are some very negligible risks with my recommendation above. The worst scenario I can imagine involves a malicious airline using information to actually prevent you from making your connection, if you’re travelling with your family – because they assume you’ll be too slow.

Personally, this seems like a very small risk to me, whereas the potential benefits are huge for the entire industry. The time savings and smoother experience will benefit everyone.

Airlines already collect a lot of information. Adding more information voluntarily and proactively seems to be relatively non-risky. Answering feedback surveys and filling out relevant information before the flights can help airlines plan better turnarounds and will improve your trip experience, and I think it’s worth our time and effort to help airlines make our trips easier.
