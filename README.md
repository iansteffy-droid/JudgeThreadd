# JudgeThreadd
### Catch an unreliable AI before it goes live.

LLM-as-a-Judge

A continuous integration testing tool to evaluate an agent before it reaches production.  

An untested RAG system deployed to production can lead to "silent failures" where the AI hallucinates incorrect return policies, breaches brand safety, or provides bad financial advice, which damages user trust and incurs significant liability. 

## How to use

1. Send your agents data to JudgeThreadd via an HTTP endpoint. 
2. Send a JSON payload containing the original user query, the exact context documents your agent retrieved, and the final answer your agent generated. 

The JudgeThreadd pipeline ingests that payload, runs the parallel judges from our Council of Judges, and streams the evaluation & scores back to the JudgeThreadd UI dashboard.