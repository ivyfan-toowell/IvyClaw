import os
import infra.settings

print("TRACING:", os.environ.get("LANGSMITH_TRACING"))
print("KEY:", os.environ.get("LANGSMITH_API_KEY", "")[:10])
print("PROJECT:", os.environ.get("LANGSMITH_PROJECT"))