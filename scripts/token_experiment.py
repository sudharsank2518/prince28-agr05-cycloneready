"""Compare estimated token counts for English and Tamil text."""

from cycloneready.llm.gateway import estimate_tokens

samples = {
    "English": (
        "CycloneReady provides cyclone preparedness information "
        "and helps people understand emergency safety instructions."
    ),
    "Tamil": (
        "சைக்ளோன் ரெடி புயல் முன்னெச்சரிக்கை தகவல்களை வழங்கி "
        "அவசர கால பாதுகாப்பு வழிமுறைகளை புரிந்துகொள்ள உதவுகிறது."
    ),
}

print("=" * 65)
print("CycloneReady - English and Tamil Token Estimation Experiment")
print("=" * 65)

results = {}

for language, sentence in samples.items():
    character_count = len(sentence)
    token_count = estimate_tokens(sentence)

    results[language] = token_count

    print(f"\nLanguage: {language}")
    print(f"Text: {sentence}")
    print(f"Characters: {character_count}")
    print(f"Estimated tokens: {token_count}")

print("\n" + "=" * 65)
print("COMPARISON")
print("=" * 65)

print("English estimated tokens:", results["English"])
print("Tamil estimated tokens:", results["Tamil"])

if results["English"] > 0:
    ratio = results["Tamil"] / results["English"]
    print(f"Tamil / English token estimate ratio: {ratio:.2f}")

print("\nNote: These are approximate character-based estimates,")
print("not exact Gemini or Groq tokenizer measurements.")
