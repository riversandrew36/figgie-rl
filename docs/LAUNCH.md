# Launch materials

Publish only after confirming the live demo and developer quickstart work.

## Announcement

I built Figgie Learning Lab, an independent educational project inspired by
Jane Street's Figgie. Start with the daily deal. Everyone gets the same
starting deal for a one-minute round, and you can share your result without
revealing the goal. The guided round teaches bidding, offering, and settlement.

Start at Beginner, try the original styles at Intermediate, or watch the
Expert candidates in Advanced (preview). Watch mode can run twenty seeded
tier battles. The difficulty lineups are scripted and come from paired
development and held-out ratings.

Try either of the two PPO seats in the Lab market. One receives the goal on
purpose, and the other trades without hints. **What the AI learned** shows
the Python training curves and a separate browser benchmark. The Python
quickstart shows how to train and compare your own policies.

Demo: https://riversandrew36.github.io/figgie-rl/
Source: https://github.com/riversandrew36/figgie-rl
Official Figgie: https://www.figgie.com/
Jane Street's gameplay video: https://www.youtube.com/watch?v=q2jjJudrEnc&t=13s

## 45–60 second recording

- 0–8s: show the Beginner table, Learn the basics, and the daily deal.
- 8–20s: start the daily deal, lock a goal prediction, and place a quote.
- 20–35s: cut to settlement and show the result card, streak, and coach.
- 35–48s: switch to Watch, run Advanced vs Intermediate, and show the
  summary. Identify Advanced as a preview.
- 48–60s: copy the spoiler-free daily result and point to the quickstart.

Ask five to ten early testers to try the demo without instructions, explain a
round's outcome, and follow the RL guide. Use their feedback before a broader
announcement. Posting to communities and contacting Jane Street are manual steps.

## Launch checklist

- [ ] Open the live demo under the `/figgie-rl/` prefix. Confirm all static
  assets load and the game starts.
- [ ] Paste the live URL into a social preview tool and confirm the title,
  description, and preview image.
- [ ] Check the daily deal on both sides of 00:00 UTC and open a dated
  practice link.
- [ ] Block browser storage and finish a daily round. Confirm the page explains
  that the result was not saved.
- [ ] Play and finish a round with only the keyboard.
- [ ] Check the hero, market, coach, and research charts at 375px.
- [ ] Verify Jane Street credit and both official links in the first viewport.
- [ ] Confirm the arena makes only same-origin requests through a full round.
  Opening an external credit or documentation link is an explicit navigation.
