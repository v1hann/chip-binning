# Why an i5 and an i7 Are Often the Same Chip

I built a simulator that makes thousands of chips with realistic manufacturing variation, works out how fast each one runs and how much power it uses, and then sorts them into products the way chip companies actually do.

!\[Wafer sorted into products](figures/1\_wafer\_bin\_map.png)

## Why I built this

This came straight out of [https://github.com/v1hann/wafer-yield-sim](https://github.com/v1hann/wafer-yield-sim). There, a chip was either dead or alive. But while reading about it, I realised the chips that survive aren't all equal either. Some come out faster, some slower, some waste more power. And chip companies make money from that: they test every chip and sell the better ones as premium products. I wanted to see how much that sorting is actually worth, so I simulated it from the transistor level up.

## The idea, simply

No two chips come out of a factory identical. Tiny differences in how the transistors are printed make some chips faster than others.

Companies don't throw the slower chips away. They test every single one and sort it: the best ones become the expensive product, the slower ones become the cheaper product. That's why an i5 and an i7 are often the same piece of silicon. One just came out a little better.

They also save chips that are partly broken. If one core has a defect, they switch that core off and sell the chip as a cheaper version with fewer cores.

## What I built

1. **Variation in layers.** Every chip gets its own small differences in transistor size and in the voltage at which its transistors switch on. I added these the way real factories think about them:

   * a pattern across the wafer (chips near the edge come out slightly worse)
   * differences from one wafer to the next
   * random chip-to-chip differences
   * tiny differences between paths inside the same chip
2. **Speed.** A chip has hundreds of critical signal paths and can only run as fast as its slowest one, like a convoy that moves at the speed of its slowest truck. So I simulate 200 paths per chip and take the slowest.
3. **Power.** Every chip uses power to switch, plus some it just leaks while switched on. Leakage grows very fast as the switch-on voltage drops.
4. **Defects.** Random defects land on each chip. If one hits a core, that core can be switched off. If it hits the shared part of the chip, the chip is scrap.
5. **Sorting.** Every chip gets the most valuable product it qualifies for: enough working cores, fast enough, and under the power limit at that speed.
6. **Comparing strategies.** I compare the money made per wafer if you sell only one product versus if you sort chips into tiers.
7. **An interactive app.** A Streamlit dashboard where you can change the amount of variation, the power limit and the prices and see everything update.

## What I found

**Sorting is worth a lot.** Selling chips in three speed tiers earns about 31% more per wafer than the best single product. Saving partly broken chips as 6-core parts takes it to about 38%.

!\[Revenue by strategy](figures/3\_revenue\_by\_strategy.png)

**Fast chips are leaky chips.** This was the most interesting part for me. The same tiny differences that make a transistor faster also make it leak more. So about 20% of the chips that were fast enough for the top product got downgraded because they'd use too much power. The top tier is limited by power, not just speed.

!\[Speed vs leakage](figures/2\_speed\_vs\_leakage.png)

**The best chips come from the centre of the wafer.** 26% of chips near the centre make the top tier, against 5% at the edge. Some steps in manufacturing are less even at the edge of the wafer, so edge chips come out slower.

**Sorting helps most when variation is moderate.** I expected that the messier the factory, the more sorting would be worth. That's not what happened. With very little variation, most chips are alike, so there's not much to sort. With a lot of variation, too many chips fail every tier, and sorting can't save them. The benefit is biggest in between.

!\[Variation sensitivity](figures/4\_variation\_sensitivity.png)

## Things I had to think about

**Why are fast chips leakier?** A slightly shorter transistor, or one with a lower switch-on voltage, pushes more current, so it's faster. But it also lets more current sneak through when it's supposed to be off. Same cause, both effects.

**Why does the slowest path set the speed?** Every calculation has to finish within one clock tick. If even one path is late, the chip makes errors. So the clock can only go as fast as the slowest path allows.

**Why not just sell the top product?** Only about 12% of chips make it. Throwing the rest away wastes most of the wafer. That's the first bar in the revenue chart.

**How much do I trust the numbers?** The overall pattern more than the exact figures. Variation sizes, power limits and prices are my assumptions (listed below). Change them in the app and the percentages move, but the main findings hold up.

## Assumptions (you can change most of these in the app)

|Parameter|Default|Note|
|-|-|-|
|Supply voltage / switch-on voltage|0.9 V / 0.30 V|typical for a modern process|
|Speed formula|alpha-power law, α = 1.3|standard for short transistors|
|Edge effect|+3% transistor length, +15 mV at the edge|assumption|
|Random chip-to-chip variation|1.5% length, 12 mV|assumption|
|Critical paths per chip|200|assumption|
|Defect density|0.10 per cm²|same as the yield project|
|Products|Pro 3.8 GHz / Plus 3.5 / Base 3.2 (8-core, 85 W); Lite 3.2 GHz (6-core, 65 W)|made-up product line|
|Prices|$450 / $330 / $250 / $180|made-up|

## Run it yourself

```bash
pip install -r requirements.txt
python make\_figures.py              # makes all the figures and figures/results.txt
python -m streamlit run app.py      # opens the interactive app
```

## What I want to add next

* Letting each chip run at its own best voltage instead of one fixed voltage, which modern chips actually do.
* Picking the speed cut-offs for each product automatically to make the most money.
* Testing cost: in reality testing every chip isn't free, so how much testing is worth it?

## Files

* `binsim.py`: the engine (variation, speed, power, defects, sorting, revenue)
* `make\_figures.py`: runs everything and saves the figures and numbers
* `app.py`: the interactive Streamlit app

