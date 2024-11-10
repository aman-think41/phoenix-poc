import json
import os
from dotenv import load_dotenv
import pandas as pd
from phoenix import Client

from phoenix.otel import register


from phoenix.evals import OpenAIModel, llm_classify
from phoenix.trace import SpanEvaluations

px_client = Client(endpoint="http://localhost:6006")

load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

tracer_provider = register(
  project_name="default",
  endpoint="http://0.0.0.0:6006/v1/traces"
)
questions = []

with open("questions.json", "r") as f:
    questions = json.load(f)


df = None

with open("phoenix_data.json", "r") as f:
    df = pd.DataFrame(json.load(f))

try:
    dataset = px_client.get_dataset(name="chat-data")
except:
    dataset = px_client.upload_dataset(
        dataset_name="chat-data",
        dataframe=df,
        input_keys=["question", "chat_history"],
        output_keys="answer"
    )

eval_model = OpenAIModel(model="gpt-4o-mini", api_key=os.getenv("OPENAI_API_KEY"))

guidelines = None
with open("guidelines.txt",'r') as f:
    guidelines = f.read()

evaluation_system_prompt = f"""
We have a set of guidelines for how to respond to questions
[BEGIN GUIDELINES]
{guidelines}
[END GUIDELINES]
You have to evaluate this step by step.
Step 1 is to understand the question and the guidelines.
Step 2 is to deduce whether the answer is in compliance with the guidelines.
Step 3 is to give a boolean value True or False based on how well the answer adheres to the guidelines, True being compliant and False being non-compliant.

You can be lenient in the case of length and brevity of the answer
Give the reason for your score in the reason field.
"""

evaluation_prompt = """
Evaluate this conversation turn according to the instructions provided earlier
[BEGIN DATA]
************
[Question]: {question}
************
[Answer]: {answer}
************
[Chat History]: {chat_history}
[END DATA]
"""

rails = ["True", "False"]

premise_score = llm_classify(
    dataframe=df,
    template=evaluation_prompt,
    model=eval_model,
    rails=rails,
    provide_explanation=True,
    include_response=True,
    system_instruction=evaluation_system_prompt
)
# Ensure the dataframe has the required index
premise_score.reset_index(drop=True, inplace=True)  # Reset the index
premise_score['context.span_id'] = range(len(premise_score))  # Add a context.span_id column with sequential values
premise_score.set_index('context.span_id', inplace=True)  # Set context.span_id as the new index

premise_score.to_csv("premise_score.csv")
with open("premise_score.json", "w") as f:
    json.dump(premise_score.to_dict(), f)

px_client.log_evaluations(
    SpanEvaluations(eval_name="Your Eval Display Name", dataframe=premise_score)
)