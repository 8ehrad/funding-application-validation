import torch
import transformers
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Initialize the pipeline once
model_id = "meta-llama/Meta-Llama-3-8B-Instruct"
pipeline = transformers.pipeline(
    "text-generation",
    model=model_id,
    model_kwargs={"torch_dtype": torch.bfloat16},
    device_map="auto",
)

# Create a FastAPI app
app = FastAPI()


class Message(BaseModel):
    content: str


@app.post("/generate")
def generate_text(message: Message):
    try:
        terminators = [
            pipeline.tokenizer.eos_token_id,
            pipeline.tokenizer.convert_tokens_to_ids("<|eot_id|>"),
        ]
        outputs = pipeline(
            [{"role": "user", "content": message.content}],
            max_new_tokens=256,
            eos_token_id=terminators,
            do_sample=True,
            temperature=0.6,
            top_p=0.9,
        )
        return {"response": outputs[0]["generated_text"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
