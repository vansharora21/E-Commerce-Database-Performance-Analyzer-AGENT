import asyncio
import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding='utf-8')


from agent.intent_detector import IntentDetector

async def run_evaluation():
    cases_path = Path(__file__).parent / "intent_cases.json"
    with open(cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    detector = IntentDetector()
    passed = 0
    total = len(cases)

    print(f"Running intent detection evaluation on {total} cases...")
    print("=" * 60)

    for i, case in enumerate(cases, 1):
        q = case["question"]
        expected_compound = case.get("is_compound", False)
        
        print(f"\nCase {i}: {q!r}")
        print(f"Expected is_compound: {expected_compound}")
        
        try:
            result = await detector.detect(q)
            print(f"Actual is_compound:   {result.is_compound}")
            print(f"Detected Intent:      {result.intent.value} ({result.time_period.value})")
            if result.is_compound:
                print("Sub-intents:")
                for s in result.sub_intents:
                    print(f"  - {s.intent.value} ({s.time_period.value}) entities={s.entities}")
            
            # Assert check
            if result.is_compound == expected_compound:
                print("Result: ✅ PASSED")
                passed += 1
            else:
                print("Result: ❌ FAILED")
        except Exception as e:
            print(f"Result: ❌ ERROR: {e}")

    print("\n" + "=" * 60)
    accuracy = passed / total if total > 0 else 0
    print(f"Evaluation Complete: {passed}/{total} passed. Accuracy: {accuracy:.0%}")
    return accuracy

if __name__ == "__main__":
    asyncio.run(run_evaluation())
