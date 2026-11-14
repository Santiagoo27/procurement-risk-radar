---
title: Procurement Risk Radar API
emoji: 📑
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
license: mit
short_description: Amendment risk for Colombian public contracts at signing time
---

# Procurement Risk Radar API

Estimates, at signing time, the probability that a Colombian public contract will later
receive a value addition or a time extension. The model is LightGBM, trained on 3.5M SECOP II
contracts and calibrated.

> Scores are statistical estimates for analysis, not allegations of wrongdoing.

- Interactive docs: `/docs`
- Source code, data audit and model card: https://github.com/Santiagoo27/procurement-risk-radar
