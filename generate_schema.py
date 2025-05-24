import os
import re
import json
from pathlib import Path

# used in schema output
pattern_1_65535 = '([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])'

def eprint(msg, *args, **kwargs):
  print(msg, *args, file=os.sys.stderr, **kwargs)

def parse_usage_file(file_path):
  with open(file_path, 'r', encoding='utf-8') as f:
    lines = [line for line in f.readlines() if line.strip()]

  # 0001 "Generic Desktop"
  page_match = re.match(r'([0-9a-fA-F]{4})\s+"([^"]+)"', lines[0])
  if not page_match:
    return None

  if len(lines) < 2:
    eprint(f"Warning: {file_path} has no usages")
    return None

  page_id = page_match.group(1)
  page_name = page_match.group(2)

  # if next non empty line is like `0001:FFFF Sel ...`
  # this is a ranged page

  # 0001:FFFF Sel "ENUM_{n}"
  ranged_page_match = re.match(r'([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s+\S+\s+"([^"]+)\{n\}"', lines[1])
  if ranged_page_match:
    usages_start = ranged_page_match.group(1)
    usages_end = ranged_page_match.group(2)
    usages_name = ranged_page_match.group(3)

    return {
      'id': page_id,
      'name': page_name,
      'range': {
        'start': int(usages_start, 16),
        'end': int(usages_end, 16),
        'name': usages_name
      }
    }

  usages = []
  for line in lines[1:]:
    usage_match = re.match(r'^([0-9a-fA-F]{2})\s+(?:Sel|[A-Z,]+)\s+"([^"]+)"', line)
    if usage_match:
      usage_name = usage_match.group(2)
      usages.append(usage_name)

  return {
    'id': page_id,
    'name': page_name,
    'usages': sorted(usages)
  }

def generate_schema_enums():
  pages_dir = Path('hid-usage-tables/pages')
  usage_pages = []

  for file in sorted(pages_dir.glob('*.txt')):
    result = parse_usage_file(file)
    if result:
      usage_pages.append(result)

  # Generate schema definitions
  definitions = {
    'usagePageEnum': {
      'type': 'string',
      'enum': sorted(page['name'] for page in usage_pages)
    }
  }

  # Add each page's usages
  for page in usage_pages:
    name = page['name']
    safe_name = re.sub(r'[^a-zA-Z0-9]', '', name)
    enum_name = f"{safe_name}UsageEnum"

    if 'range' in page:
      range_name = page['range']['name']
      if page['range']['start'] != 0 and page['range']['end'] != 0xffff:
        print(f"Warning: {name} has a range that is not 0-0xffff")
      else:
        definitions[enum_name] = {
          'type': 'string',
          'pattern': f"^{range_name}({pattern_1_65535})$",
          'description': f"{name} usage values in format '{range_name}{{n}}' where n is a number between 1 and 65535 (0xffff)"
        }
    else:
      definitions[enum_name] = {
        'type': 'string',
        'enum': page['usages']
      }

  # usageArray: array of [page, usage]
  usage_array_refs = []

  # usageRangeArray: array of [page, usage, usage]
  usage_range_array_refs = []

  for page in usage_pages:
    safe_name = re.sub(r'[^a-zA-Z0-9]', '', page['name'])
    enum_name = f"{safe_name}UsageEnum"

    usage_array_refs.append({
      'type': 'array',
      'items': [
        {'const': page['name']},
        {'$ref': f'#/definitions/{enum_name}'}
      ],
      'minItems': 2,
      'maxItems': 2
    })

    usage_range_array_refs.append({
      'type': 'array',
      'items': [
        {'const': page['name']},
        {'$ref': f'#/definitions/{enum_name}'},
        {'$ref': f'#/definitions/{enum_name}'}
      ],
      'minItems': 3,
      'maxItems': 3
    })

  definitions['usageArray'] = {
    'oneOf': usage_array_refs
  }
  
  definitions['usageRangeArray'] = {
    'oneOf': usage_range_array_refs
  }

  return definitions

if __name__ == '__main__':
  definitions = generate_schema_enums()
  generated_enums = json.dumps(definitions, indent=2)

  # trim first and last braces, align indentation and add trailing comma
  generated_enums = generated_enums[1:-1].strip()
  generated_enums = '\n'.join('  ' + line for line in generated_enums.splitlines())
  generated_enums += ','

  # generate `waratah.schema.json` from `schema_template.jsonc`,
  # replacing `/* GENERATED_ENUMS */` with the generated enums
  schema_template_path = Path('schema_template.jsonc')
  schema_output_path = Path('waratah.schema.json')

  if not schema_template_path.exists():
    eprint(f"error: {schema_template_path} does not exist")
    exit(1)

  with open(schema_template_path, 'r', encoding='utf-8') as template_file:
    template_content = template_file.read()

  if '/* GENERATED_ENUMS */' not in template_content:
    eprint("error: missing '/* GENERATED_ENUMS */'")
    exit(1)

  schema_content = template_content.replace('/* GENERATED_ENUMS */', generated_enums)
  with open(schema_output_path, 'w', encoding='utf-8') as output_file:
    output_file.write(schema_content)
