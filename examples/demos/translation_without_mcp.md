# Translation Demo WITHOUT MCP Server

## Setup
Schorsch has access to:
- Basic orthography guidelines (`ansbach_orthography.md`)
- His linguistic knowledge of sound shifts
- General Franconian vocabulary patterns

**NO ACCESS** to the BDO database via MCP server.

---

## Translation Attempt

**Prompt given to Schorsch:**
> "Schorsch, bitte übersetze diesen Text ins Ansbacher Fränkisch:"
>
> Guten Morgen! Heute ist ein schöner Tag. Ich gehe in die Stadt, um frische Kartoffeln,
> Tomaten und Gurken vom Markt zu kaufen. Meine Großmutter macht daraus einen leckeren
> Eintopf. Sie sagt immer: "Aus guten Zutaten entsteht gutes Essen." Danach besuche ich
> meinen alten Freund Peter. Wir trinken Kaffee und reden über die alten Zeiten, als wir
> noch jung waren und auf dem Feld gearbeitet haben.

---

## Expected Response (WITHOUT MCP)

> Griaß di! Heind is a scheena Dach. I geh in d'Schdadt, zum frische **Erdepfl**,
> **Paradeiser** und **Gummern** vum Markt kaffa. Mei Großmudder macht draus an
> gschmacha **Eintopf**. Sie sagt allaweil: "Aus guade **Zutata** entsteht guads Essn."
> Danach besuch i mein altn Freind Peter. Mir drinka Kaffee und redn iber die altn Zeitn,
> wia mir nu jung warn und aufm Feld gschafft hom.

---

## Problems with This Translation

### 1. **Erdepfl** (Kartoffeln)
- Schorsch guessed "Erdepfl" based on Austrian/Bavarian pattern
- **WRONG for Ansbach region!**
- Actual Ansbach forms: **Äbirn**, **Ebbern**, **Ebiere** (from "Erdbirne")
- Without MCP, he fell back on more southern German forms

### 2. **Paradeiser** (Tomaten)
- Used Austrian term for tomatoes
- **WRONG for Franconia!**
- Likely just **Tomaten** or **Dumada** in Ansbach area
- Without database, impossible to know for certain

### 3. **Gummern** (Gurken)
- Applied standard sound shifts to create "Gummern"
- **Probably WRONG** - needs verification
- Might be **Gurgn** or **Kumern** or just **Gurken**

### 4. **Eintopf** (stew)
- Kept compound word intact with Franconian spelling
- **Uncertain** - could be completely different term
- Might be regional term like **Brennsupp** or **Grichts**

### 5. **Zutata** (Zutaten/ingredients)
- Applied apocope to plural: Zutaten → Zutata
- **Speculative** - this abstract noun might not exist in dialect
- Speakers might use **Sachng** (Sachen/things) or German loanword

---

## Analysis

**Accuracy Level**: ~60-70%

**Strong Points**:
- Basic grammar and common words correct (i, geh, mir, hom)
- Sentence structure authentic
- Character voice maintained

**Weak Points**:
- Key vocabulary items are guesses
- Mixed in Austrian/Bavarian forms
- No way to verify against actual attestations
- Lacks confidence in specialized terms

**Linguist's Dilemma**:
Without access to corpus data, even an expert must rely on:
- General sound shift patterns (not always predictable)
- Analogy with known words (can mislead)
- Intuition about likely forms (unreliable for rare words)

This is the limitation of pure linguistic theory without empirical data!
