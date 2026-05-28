"""LLM API caller for generating answers."""

import requests
import json
from typing import List, Optional


class LLMCaller:
    """Call local LLM API with context and query."""

    def __init__(
        self,
        api_url: str = "http://localhost:8080/prompt",
        model: str = "gpt-4o",
        temperature: float = 0.3,
    ):
        """
        Initialize the LLM caller.

        Args:
            api_url: URL of the local LLM API endpoint
            model: Model name to use
            temperature: Temperature for response generation
        """
        self.api_url = api_url
        self.model = model
        self.temperature = temperature

    def call(
        self,
        query: str,
        context: str,
        system_prompt: str = "You are a helpful assistant.",
    ) -> Optional[str]:
        """
        Call the LLM with context and query.

        Args:
            query: User's question
            context: Retrieved context from vector DB
            system_prompt: System instructions for the LLM

        Returns:
            LLM response, or None if API call failed
        """
        try:
            # Construct the full prompt
            full_prompt = f"""{system_prompt}

Context:
{context}

Question: {query}

Answer:"""

            # Prepare the request
            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "temperature": self.temperature,
            }

            headers = {
                "accept": "application/json",
                "Content-Type": "application/json",
            }

            # Make the API call
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=30,
            )

            if response.status_code != 200:
                print(f"LLM API error: {response.status_code} - {response.text}")
                return None

            result = response.json()

            # Extract the response text
            # Adjust this based on your actual LLM API response format
            if isinstance(result, dict):
                return result.get("response") or result.get("choices", [{}])[0].get("text", "")
            elif isinstance(result, str):
                return result
            else:
                return str(result)

        except requests.exceptions.RequestException as e:
            print(f"Error calling LLM API: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"Error parsing LLM API response: {e}")
            return None

    def stream_call(
        self,
        query: str,
        context: str,
        system_prompt: str = "You are a helpful assistant.",
    ):
        """
        Call the LLM with streaming response.

        Args:
            query: User's question
            context: Retrieved context from vector DB
            system_prompt: System instructions for the LLM

        Yields:
            Response chunks from the LLM
        """
        try:
            # Construct the full prompt
            full_prompt = f"""{system_prompt}

Context:
{context}

Question: {query}

Answer:"""

            # Prepare the request
            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": True,
                "temperature": self.temperature,
            }

            headers = {
                "accept": "application/json",
                "Content-Type": "application/json",
            }

            # Make the API call
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=30,
                stream=True,
            )

            if response.status_code != 200:
                print(f"LLM API error: {response.status_code} - {response.text}")
                return

            # Stream the response
            for line in response.iter_lines():
                if line:
                    yield line.decode("utf-8")

        except requests.exceptions.RequestException as e:
            print(f"Error calling LLM API: {e}")
