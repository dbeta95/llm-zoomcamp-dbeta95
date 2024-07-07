import streamlit as st
from openai import OpenAI
from elasticsearch import Elasticsearch

client = OpenAI(
    base_url='http://localhost:11434/v1/',
    api_key='ollama'
)


es_client = Elasticsearch('http://localhost:9200')

index_name = "course-questions"

def elastic_search(query):
    search_query = {
        "size": 5,
        "query": {
            "bool": {
                "must": {
                    "multi_match": {
                        "query": query,
                        "fields": ["question^3", "text", "section"], # The hat means three times more importance
                        "type": "best_fields"
                    }
                },
                "filter": {
                    "term": {
                        "course": "data-engineering-zoomcamp"
                    }
                }
            }
        }
    }

    response = es_client.search(index=index_name, body=search_query)

    result_docs = []
    for hit in response['hits']['hits']:
        result_docs.append(hit['_source'])

    return result_docs

def build_prompt(query, search_results):
    prompt_template = """
You're a course teaching assistant. Answer the QUESTION based on the CONTEXT from the FAQ database.
Use only the facts from the CONTEXT when answering the QUESTION.

QUESTION: {question}

CONTEXT: 
{context}
""".strip()

    context = ""
    
    for doc in search_results:
        context = context + f"section: {doc['section']}\nquestion: {doc['question']}\nanswer: {doc['text']}\n\n"
    
    prompt = prompt_template.format(question=query, context=context).strip()
    return prompt

def llm(prompt):
    response = client.chat.completions.create(
        model='phi3',
        messages=[{"role": "user", "content": prompt}]
    )
    
    return response.choices[0].message.content


# Placeholder for your RAG function
def rag(query):
    search_results = elastic_search(query)
    prompt = build_prompt(query, search_results)
    answer = llm(prompt)
    import time
    time.sleep(3)
    return answer

# Streamlit app
st.title("RAG Application")

user_input = st.text_input("Enter your query:")
ask_button = st.button("Ask")

# Loading indicator
loading_placeholder = st.empty()

if ask_button:
    loading_placeholder.text("Loading... Please wait.")
    with st.spinner("Processing your query..."):
        response = rag(user_input)
    loading_placeholder.empty()  # Clear the loading indicator
    st.write(response)