from openai import OpenAI, APIConnectionError, AuthenticationError, RateLimitError
from openai.types.chat import ChatCompletionUserMessageParam
from dotenv import load_dotenv
import os
import sys

load_dotenv()


def main() -> int:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY is not set. Add it to your .env file.")
        return 1

    client = OpenAI(api_key=api_key)
    messages: list[ChatCompletionUserMessageParam] = [
        {"role": "user", "content": "Explain what is AI simply"}
    ]

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
        )
        print(response.choices[0].message.content)
        return 0
    except RateLimitError as error:
        body_code = (
            (getattr(error, "body", {}) or {})
            .get("error", {})
            .get("code")
        )
        code = getattr(error, "code", None) or body_code
        if code == "insufficient_quota":
            print("Error: insufficient quota. Check your OpenAI plan and billing.")
        else:
            print(f"Rate limit error: {error}")
        return 1
    except AuthenticationError:
        print("Error: invalid API key. Check OPENAI_API_KEY in your .env file.")
        return 1
    except APIConnectionError:
        print("Error: could not connect to the OpenAI API. Check your internet connection.")
        return 1
    except Exception as error:
        print(f"Unexpected error: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
