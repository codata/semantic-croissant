import requests

desc = "De huidige bebouwing aan het Dompad 7 in De Lier in de gemeente Westland en de hierbij behorende bestrating zal vervangen worden door een nieuw te bouwen bedrijfs- en woonruimte. Het was op voorhand niet uit te sluiten dat bij de hiermee gepaard gaande werkzaamheden verstoring van de archeologisch bodemarchief zou optreden. Daarom heeft Archeologie Delft in opdracht van ArcheoWest BV een archeologisch bureauonderzoek en inventariserend veldonderzoek middels grondboringen uitgevoerd. Uit dit onderzoek is gebleken dat er archeologisch interessante lagen in de bodem van het plangebied aanwezig zijn."

prompt = f"Translate the ENTIRE following text to English. Do not summarize. Translate every single word until the end of the text:\n\n{desc}"

payload = {
    "model": "gemma4-croissant",
    "prompt": prompt,
    "stream": False,
    "options": {
        "num_predict": 4096
    }
}
res = requests.post("http://10.147.18.82:11435/api/generate", json=payload, timeout=600)
print(res.status_code)
print(repr(res.json().get('response')))
