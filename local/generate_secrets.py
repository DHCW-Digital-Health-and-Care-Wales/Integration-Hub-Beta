import secrets
with open(".secrets-template") as template:
  for line in template:
    print(line.rstrip() + "\"" + secrets.token_urlsafe(16) + "\"")
