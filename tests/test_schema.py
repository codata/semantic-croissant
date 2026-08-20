from jsonschema import validate
schema = {
    "type": "object",
    "properties": {
        "content": {"type": "string"},
        "jsonld_payload": {}
    }
}
validate({"content": "hi", "jsonld_payload": {"@context": "foo"}}, schema)
print("Valid!")
