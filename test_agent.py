import asyncio
from langchain_agent import run_agent
import traceback


async def main():
    print("🧪 Local LangChain Agent Test")
    print("-" * 40)

    while True:
        try:
            query = input("\nAsk something (or type 'exit'): ").strip()
            if query.lower() in {"exit", "quit"}:
                break

            print("\n⏳ Thinking...\n")
            answer = await run_agent(query)

            print("🤖 Answer:")
            print(answer)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print("❌ Error:")
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())