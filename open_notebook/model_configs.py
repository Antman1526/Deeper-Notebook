from open_notebook.language_models import (
    AnthropicLanguageModel,
    LiteLLMLanguageModel,
    OllamaLanguageModel,
    OpenAILanguageModel,
    OpenRouterLanguageModel,
    VertexAILanguageModel,
    VertexAnthropicLanguageModel,
)

LANGUAGE_MODEL_CONFIG = {
    "OLLAMA": {
        "class": OllamaLanguageModel,
        "models": [
            "mistral-nemo:latest",
            "llama3.1:8b",
            "qwen2.5:32b",
            "nemotron-mini:latest",
            "phi3.5:latest",
            "gemma2",
            "bling-phi-3.gguf",
            "granite3-dense:8b",
            "granite3-moe:latest",
            "hermes3",
            "llama3.2",
            "phi3.5:3.8b-mini-instruct-fp16",
            "phi3:14b",
            "wizardlm2",
            "zephyr",
            "solar-pro",
        ],
    },
    "OPEN_ROUTER": {
        "class": OpenRouterLanguageModel,
        "models": [
            "nvidia/llama-3.1-nemotron-70b-instruct",
            "anthropic/claude-3.5-sonnet",
            "google/gemini-flash-1.5",
        ],
    },
    "VERTEX_ANTHROPIC": {
        "class": VertexAnthropicLanguageModel,
        "models": ["claude-3-5-sonnet@20240620"],
    },
    "LITELLM": {
        "class": LiteLLMLanguageModel,
        "models": ["ollama/mistral-nemo:latest", "ollama/llama3.1:8b"],
    },
    "VERTEX_AI": {
        "class": VertexAILanguageModel,
        "models": ["gemini-1.5-flash-001", "gemini-1.5-pro-001"],
    },
    "ANTHROPIC": {
        "class": AnthropicLanguageModel,
        "models": ["claude-3-5-sonnet-20240620"],
    },
    "OPEN_AI": {"class": OpenAILanguageModel, "models": ["gpt-4o-mini", "gpt-4o"]},
}

# EMBEDDING_MODEL_CONFIG = {
#     "OPEN_AI": {
#         "class": OpenAIEmbeddingModel,
#         "models": ["text-embedding-3-large"],
#         "dimensions": [3072],
#     },
# }


def get_model_class(model_name):
    for config in LANGUAGE_MODEL_CONFIG.values():
        if model_name in config["models"]:
            return config["class"]
    raise ValueError(f"Model {model_name} not found in config")


def get_langchain_model(model_name, json=False):
    model_class = get_model_class(model_name=model_name)
    return model_class(model_name=model_name, json=json).to_langchain()
