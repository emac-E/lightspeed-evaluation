# RAG evaluation metrics explained

## Purpose of RAG metrics testing
Lightspeed-evaluation includes ragas metrics to evaluate the quality of RAG chunks in relation to the test questions. These metrics will evalute the chunks in relation to the expected answer, the question asked, and the LLM-provided answer, depending on the metric selected. The following sections go into further detail about how the metrics are calcualted, and what this might tell you about your RAG retrieval algorithms in non-technical language.


## Metric Details
### response_relevancy ()
How relevant a response is to the user's question. 
* Directly and appropriately answers the original question
* Penalizes for incomplete answers or those that include unneccessary details

How it works:
* Generates a set of Q's based on the response
* Find cosine similarity between embedding of user input (E_o) and the embedding of each generated question (E_g_i)
** `strictness` setting determines number of artifically generated questions (default 3)
* Score is the average of the cosine similary per generated question

Answer Relevancy = 1/N sum(cosine similarity(E_g_i, E_o))

NOTE: requires second LLM, doesn't require RAG chunks


### faithfulness
Factual consistency when comparing the response with the retrieved context.
Scoring is based on whether all claims can be supported by the rag chunks retrieved (leading to lower scores when hallucinations appear).

How it works:
* identify all claims in the response by breaking them into separate statements
* count number of rag chunks that will support this claim

Faithfulness = number of claims in the response supported by rag chunks / total claims in the response

NOTE: requires second LLM and RAG chunks


### context_recall
RAG retrieval metric that demonstrates completeness of retrieved information by comparing it to the question. There are llm-based and non-llm based versions of this metric available in the ragas library.

How it works:
* question is boken up into individual claims

### context_precision_with_reference


### context_precision_without_reference


### context_relevance


# Resources for learning
Documentation on metrics:
    https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/

