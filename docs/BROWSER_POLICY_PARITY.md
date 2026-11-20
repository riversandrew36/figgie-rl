# Browser policy parity gate

No learned policy is seated. The study used **MaskablePPO**, so reproducing the
actor also requires Python's action-feasibility mask. The local exporter writes
the actor layers, observation layout, hidden blocks, action decoding, and a
fixed-deal probe with raw logits and the masked argmax.

```sh
python -m scripts.export_browser_policy /tmp/figgie-policy-probe
npm test
```

The step-3 median seed is 902. Both actor exports use seed 902. The goal-shown
actor is 330,696 bytes and the no-aids actor is 329,184 bytes. Only the diagnostic
step-3 fixture is checked in, under `tests/browser/fixtures/`. Neither network
is shipped to the site.

The gate fails before an argmax comparison. The probe posts one $8 Spades offer,
then lets it age with no other actions. At the required rate of two browser ticks
per learner decision, browser tick 8 corresponds to Python decision 4. Python
still has the offer at decisions 4–7 while the browser has already expired it.
The observed best ask differs by 0.4 after scaling, and availability also
differs. The Python quote lifetime is eight learner decisions. The browser
lifetime is eight 250 ms ticks. The Node gate replays the offer through the
existing browser engine and checks the four failing decisions.

An encoder cannot reconstruct an executable offer that has expired. Matching
the training timeline would require changing the live quote lifetime or adding
a separate market for the learned seat. Either would change the requested
market semantics. The exports are diagnostic and there are no browser PPO
benchmark numbers.
