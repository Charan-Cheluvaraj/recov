from typing import List

def load_embedding_model(model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
    """Load sentence-transformer model instance."""
    raise NotImplementedError("load_embedding_model is deferred in Prompt 1.")

def generate_text_embedding(text: str, model=None) -> List[float]:
    """Generate dense 384-dimensional vector embedding for text segment."""
    raise NotImplementedError("generate_text_embedding is deferred in Prompt 1.")
