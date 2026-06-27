import io
with io.open('.github/workflows/ci.yml', 'r', encoding='utf-8', errors='ignore') as f:
    c = f.read()
old = '--cov=. --cov-config=.coveragerc\\'
new = '--cov=. --cov-config=.coveragerc \\'
c = c.replace(old, new)
with io.open('.github/workflows/ci.yml', 'w', encoding='utf-8') as f:
    f.write(c)
print('Fixed spacing')
