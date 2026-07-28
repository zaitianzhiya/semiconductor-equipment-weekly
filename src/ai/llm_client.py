"""LLM client — multi-provider abstraction (Gemini, DeepSeek, Qwen, Anthropic, OpenAI)."""

import os

import requests


class LLMClient:
    """Detect available LLM provider from environment variables and provide a
    unified chat() interface."""

    def __init__(self, model: str = None):
        self.model = model
        self.provider = self._detect_provider()
        self.label = f"{self.provider}/{self.model or 'default'}"

    def _detect_provider(self) -> str:
        if os.environ.get("GEMINI_API_KEY"):
            return "gemini"
        if os.environ.get("DEEPSEEK_API_KEY"):
            return "deepseek"
        if os.environ.get("QWEN_API_KEY"):
            return "qwen"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        raise RuntimeError(
            "No LLM API key found. Set one of: GEMINI_API_KEY, DEEPSEEK_API_KEY, "
            "QWEN_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY"
        )

    def chat(self, system_prompt: str, user_message: str, temperature: float = 0.7) -> str:
        if self.provider == "gemini":
            return self._chat_gemini(system_prompt, user_message, temperature)
        elif self.provider == "deepseek":
            return self._chat_openai_compat(
                system_prompt, user_message, temperature,
                base_url="https://api.deepseek.com",
                model=self.model or "deepseek-chat",
            )
        elif self.provider == "qwen":
            return self._chat_openai_compat(
                system_prompt, user_message, temperature,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model=self.model or "qwen-plus",
            )
        elif self.provider == "anthropic":
            return self._chat_anthropic(system_prompt, user_message, temperature)
        elif self.provider == "openai":
            return self._chat_openai_compat(
                system_prompt, user_message, temperature,
                base_url=None, model=self.model or "gpt-4o",
            )
        raise ValueError(f"Unknown provider: {self.provider}")

    def _chat_gemini(self, system_prompt: str, user_message: str, temperature: float) -> str:
        combined = f"{system_prompt}\n\n---\n\n{user_message}"
        resp = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            params={"key": os.environ["GEMINI_API_KEY"]},
            json={
                "contents": [{"parts": [{"text": combined}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": 8192,
                },
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        if "candidates" in data and data["candidates"]:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        raise RuntimeError(f"Gemini unexpected response: {data}")

    def _chat_openai_compat(
        self, system_prompt: str, user_message: str, temperature: float,
        base_url: str = None, model: str = "",
    ) -> str:
        url = (
            f"{base_url}/chat/completions"
            if base_url
            else "https://api.openai.com/v1/chat/completions"
        )
        key = (
            os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("QWEN_API_KEY")
            or os.environ.get("OPENAI_API_KEY", "")
        )
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": temperature,
                "max_tokens": 8192,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _chat_anthropic(self, system_prompt: str, user_message: str, temperature: float) -> str:
        import anthropic

        return (
            anthropic.Anthropic()
            .messages.create(
                model=self.model or "claude-sonnet-4-20250514",
                max_tokens=8192,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            .content[0]
            .text
        )
