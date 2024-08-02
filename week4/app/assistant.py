import os
import time
import json
import google.generativeai as genai

from functools import reduce
from openai import OpenAI

from elasticsearch import Elasticsearch
from sentence_transformers import SentenceTransformer


ELASTIC_URL = os.getenv("ELASTIC_URL", "http://elasticsearch:9200")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434/v1/")
#OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "your-api-key-here")
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

safety_settings={
    'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE',
    'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE',
    'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE',
    'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE'
}
generation_config=genai.types.GenerationConfig(
    candidate_count=1, 
    temperature=0
)

es_client = Elasticsearch(ELASTIC_URL)
ollama_client = OpenAI(base_url=OLLAMA_URL, api_key="ollama")
genai.configure(api_key=GOOGLE_API_KEY)
#openai_client = OpenAI(api_key=OPENAI_API_KEY)

model = SentenceTransformer("multi-qa-MiniLM-L6-cos-v1")


def elastic_search_text(query, course, index_name="course-questions"):
    search_query = {
        "size": 5,
        "query": {
            "bool": {
                "must": {
                    "multi_match": {
                        "query": query,
                        "fields": ["question^3", "text", "section"],
                        "type": "best_fields",
                    }
                },
                "filter": {"term": {"course": course}},
            }
        },
    }

    response = es_client.search(index=index_name, body=search_query)
    return [hit["_source"] for hit in response["hits"]["hits"]]


def elastic_search_knn(field, vector, course, index_name="course-questions"):
    knn = {
        "field": field,
        "query_vector": vector,
        "k": 5,
        "num_candidates": 10000,
        "filter": {"term": {"course": course}},
    }

    search_query = {
        "knn": knn,
        "_source": ["text", "section", "question", "course", "id"],
    }

    es_results = es_client.search(index=index_name, body=search_query)

    return [hit["_source"] for hit in es_results["hits"]["hits"]]


def build_prompt(query, search_results):
    prompt_template = """
You're a course teaching assistant. Answer the QUESTION based on the CONTEXT from the FAQ database.
Use only the facts from the CONTEXT when answering the QUESTION.

QUESTION: {question}

CONTEXT: 
{context}
""".strip()

    context = "\n\n".join(
        [
            f"section: {doc['section']}\nquestion: {doc['question']}\nanswer: {doc['text']}"
            for doc in search_results
        ]
    )
    return prompt_template.format(question=query, context=context).strip()


def llm(prompt, model_choice):
    start_time = time.time()
    if model_choice.startswith('ollama/'):
        response = ollama_client.chat.completions.create(
            model=model_choice.split('/')[-1],
            messages=[{"role": "user", "content": prompt}]
        )
        answer = response.choices[0].message.content
        tokens = {
            'prompt_tokens': response.usage.prompt_tokens,
            'completion_tokens': response.usage.completion_tokens,
            'total_tokens': response.usage.total_tokens
        }
    # elif model_choice.startswith('openai/'):
    #     response = openai_client.chat.completions.create(
    #         model=model_choice.split('/')[-1],
    #         messages=[{"role": "user", "content": prompt}]
    #     )
    #     answer = response.choices[0].message.content
    #     tokens = {
    #         'prompt_tokens': response.usage.prompt_tokens,
    #         'completion_tokens': response.usage.completion_tokens,
    #         'total_tokens': response.usage.total_tokens
    #     }
    elif model_choice.startswith("google/"):               

        model = genai.GenerativeModel(model_choice.split('/')[-1])
        responses = model.generate_content(
            contents = prompt,
            safety_settings = safety_settings,
            generation_config = generation_config
        )
        answer = "".join(response.text for response in responses)
        prompt_tokens = reduce(lambda a, b: a + b, [
            response.usage_metadata.prompt_token_count for response in responses
        ])
        completion_tokents = reduce(lambda a, b: a + b, [
            response.usage_metadata.candidates_token_count for response in responses
        ])
        
        total_tokents = reduce(lambda a, b: a + b, [
            response.usage_metadata.total_token_count for response in responses
        ])

        tokens = {
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokents,
            'total_tokens': total_tokents
        }
        
    else:
        raise ValueError(f"Unknown model choice: {model_choice}")
    
    end_time = time.time()
    response_time = end_time - start_time
    
    return answer, tokens, response_time


def evaluate_relevance(question, answer):
    prompt_template = """
    You are an expert evaluator for a Retrieval-Augmented Generation (RAG) system.
    Your task is to analyze the relevance of the generated answer to the given question.
    Based on the relevance of the generated answer, you will classify it
    as "NON_RELEVANT", "PARTLY_RELEVANT", or "RELEVANT".

    Here is the data for evaluation:

    Question: {question}
    Generated Answer: {answer}

    Please analyze the content and context of the generated answer in relation to the question
    and provide your evaluation in parsable JSON without using code blocks:

    {{
      "Relevance": "NON_RELEVANT" | "PARTLY_RELEVANT" | "RELEVANT",
      "Explanation": "[Provide a brief explanation for your evaluation]"
    }}
    """.strip()

    prompt = prompt_template.format(question=question, answer=answer)
    evaluation, tokens, _ = llm(prompt, 'google/gemini-1.5-pro')
    
    try:
        json_eval = json.loads(evaluation)
        return json_eval['Relevance'], json_eval['Explanation'], tokens
    except json.JSONDecodeError:
        return "UNKNOWN", "Failed to parse evaluation", tokens


def calculate_google_cost(model_choice, tokens):
    google_cost = 0

    if model_choice == 'google/gemini-1.5-flash':
        google_cost = (tokens['prompt_tokens'] * 0.35 + tokens['completion_tokens'] * 1.05) / 1000000
    elif model_choice == 'google/gemini-1.5-pro':
        google_cost = (tokens['prompt_tokens'] * 3.5 + tokens['completion_tokens'] * 10.5) / 1000000

    return google_cost


def get_answer(query, course, model_choice, search_type):
    if search_type == 'Vector':
        vector = model.encode(query)
        search_results = elastic_search_knn('question_text_vector', vector, course)
    else:
        search_results = elastic_search_text(query, course)

    prompt = build_prompt(query, search_results)
    answer, tokens, response_time = llm(prompt, model_choice)
    
    relevance, explanation, eval_tokens = evaluate_relevance(query, answer)

    google_cost = calculate_google_cost(model_choice, tokens)
 
    return {
        'answer': answer,
        'response_time': response_time,
        'relevance': relevance,
        'relevance_explanation': explanation,
        'model_used': model_choice,
        'prompt_tokens': tokens['prompt_tokens'],
        'completion_tokens': tokens['completion_tokens'],
        'total_tokens': tokens['total_tokens'],
        'eval_prompt_tokens': eval_tokens['prompt_tokens'],
        'eval_completion_tokens': eval_tokens['completion_tokens'],
        'eval_total_tokens': eval_tokens['total_tokens'],
        'google_cost': google_cost
    }