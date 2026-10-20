from pathlib import Path
p = Path(r'D:/rapport_achat/config/settings.py')
s = p.read_text(encoding='utf-8')
# remove whitenoise
s = s.replace('    \"whitenoise.middleware.WhiteNoiseMiddleware\",\n', '')
# insert
marker = '    \"django.middleware.security.SecurityMiddleware\",\n'
if 'whitenoise.middleware.WhiteNoiseMiddleware' not in s and marker in s:
    s = s.replace(marker, '    \"django.middleware.security.SecurityMiddleware\",\n    \"whitenoise.middleware.WhiteNoiseMiddleware\",\n', 1)
# storage
s = s.replace('CompressedManifestStaticFilesStorage', 'CompressedStaticFilesStorage')
p.write_text(s, encoding='utf-8')