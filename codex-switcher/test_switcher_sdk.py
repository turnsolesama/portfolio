import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import switcher_core as c

EXAMPLES=Path(__file__).with_name('examples')
PY=(EXAMPLES/'deepseek.py').read_text(encoding='utf-8')
JS=(EXAMPLES/'deepseek.mjs').read_text(encoding='utf-8')


class SDKTests(unittest.TestCase):
    def parse(self,text):
        rows,notes=c.import_text(text)
        self.assertTrue(rows)
        return rows,notes

    def test_python_example(self):
        rows,notes=self.parse(PY)
        p=rows[0]['profile']
        self.assertEqual((p['base_url'],p['model'],p['reasoning_effort'],p['env_key'],p['wire_api']),
                         ('https://api.deepseek.com','deepseek-v4-pro','high','DEEPSEEK_API_KEY','responses'))
        self.assertEqual(rows[0]['secret'],'');self.assertIn('Python',notes[0])

    def test_node_example_matches_python(self):
        py,_=self.parse(PY);js,notes=self.parse(JS)
        self.assertEqual(js,py);self.assertIn('Node.js',notes[0])

    def test_markdown_fences_and_comments(self):
        for text,label in ((PY,'python'),(JS,'javascript')):
            expected,_=self.parse(text)
            actual,_=self.parse('```'+label+'\n'+text+'\n```')
            self.assertEqual(expected,actual)
        self.parse('# install dependencies yourself\n'+PY)
        self.parse('/* example only */\n// comment\n'+JS)

    def test_python_import_aliases_and_async(self):
        text=PY.replace('from openai import OpenAI','from openai import AsyncOpenAI as SDK').replace('OpenAI(', 'SDK(')
        self.parse(text)
        self.parse(PY.replace('import os','import os as env_os').replace('os.environ','env_os.environ'))
        self.parse(PY.replace('from openai import OpenAI','import openai as sdk').replace('OpenAI(', 'sdk.OpenAI('))
        self.parse('import os\nfrom openai import AsyncOpenAI\nasync def main():\n'+ '\n'.join('    '+l for l in PY.splitlines()[3:]).replace('OpenAI(', 'AsyncOpenAI(').replace('response = client.', 'response = await client.'))

    def test_node_named_import_commonjs_and_aliases(self):
        self.parse(JS.replace("import OpenAI from 'openai';", "import { OpenAI as SDK } from 'openai';").replace('new OpenAI(', 'new SDK('))
        self.parse(JS.replace("import OpenAI from 'openai';", "const OpenAI = require('openai');"))
        self.parse(JS.replace('client','service'))

    def test_variable_metadata_and_object_options(self):
        text=PY.replace('client = OpenAI(', 'BASE="https://api.deepseek.com"\nMODEL="deepseek-v4-pro"\nKEY=os.getenv("DEEPSEEK_API_KEY")\nclient = OpenAI(')
        text=text.replace('base_url="https://api.deepseek.com"','base_url=BASE').replace('model="deepseek-v4-pro"','model=MODEL').replace('api_key=os.environ.get("DEEPSEEK_API_KEY")','api_key=KEY')
        self.parse(text)
        self.parse("import OpenAI from 'openai'; const options={baseURL:'https://api.deepseek.com',apiKey:process.env.DEEPSEEK_API_KEY}; const req={model:'deepseek-v4-pro',reasoning:{effort:'high'}}; const c=new OpenAI(options); const r=await c.responses.create(req);")

    def test_python_literal_kwargs_and_js_spread(self):
        self.parse('from openai import OpenAI\noptions={"base_url":"https://api.deepseek.com"}\nrequest={"model":"deepseek-v4-pro"}\nclient=OpenAI(**options)\nclient.responses.create(**request)')
        self.parse("import OpenAI from 'openai'; const options={baseURL:'https://api.deepseek.com'}; const c=new OpenAI({...options}); c.responses.create({model:'deepseek-v4-pro'});")

    def test_environment_forms_never_read_values(self):
        for expression in ('os.getenv("DEEPSEEK_API_KEY")','os.environ["DEEPSEEK_API_KEY"]','os.environ.get("DEEPSEEK_API_KEY",None)'):
            with patch.dict('os.environ',{'DEEPSEEK_API_KEY':'DO_NOT_READ_SENTINEL'}):
                rows,notes=self.parse(PY.replace('os.environ.get("DEEPSEEK_API_KEY")',expression))
                self.assertNotIn('DO_NOT_READ_SENTINEL',repr((rows,notes)))
                self.assertEqual(rows[0]['secret'],'')
        self.parse(JS.replace('process.env.DEEPSEEK_API_KEY',"process.env['DEEPSEEK_API_KEY']"))

    def test_literal_secret_never_exported(self):
        for text in (PY.replace('os.environ.get("DEEPSEEK_API_KEY")','"FAKE_SDK_SECRET"'),JS.replace('process.env.DEEPSEEK_API_KEY',"'FAKE_SDK_SECRET'")):
            rows,notes=self.parse(text);self.assertEqual(rows[0]['secret'],'FAKE_SDK_SECRET')
            self.assertNotIn('FAKE_SDK_SECRET',c.export_profiles([rows[0]['profile']]))
            self.assertNotIn('FAKE_SDK_SECRET',str(notes))

    def test_default_openai_responses(self):
        for text in ('from openai import OpenAI\nc=OpenAI()\nc.responses.create(model="example-model")',"import OpenAI from 'openai';const c=new OpenAI();c.responses.create({model:'example-model'});"):
            rows,_=self.parse(text);p=rows[0]['profile']
            self.assertEqual(p['base_url'],'https://api.openai.com/v1')
            self.assertEqual(p['env_key'],'OPENAI_API_KEY')

    def test_generic_responses_preserves_url(self):
        for text in (PY.replace('chat.completions','responses').replace('api.deepseek.com','api.example/v1'),JS.replace('chat.completions','responses').replace('api.deepseek.com','api.example/v1')):
            rows,_=self.parse(text);self.assertEqual(rows[0]['profile']['base_url'],'https://api.example/v1')

    def test_multiple_models_and_deduplication(self):
        text='from openai import OpenAI\nc=OpenAI(base_url="https://api.deepseek.com")\nc.responses.create(model="first")\nc.responses.create(model="second")'
        rows,_=self.parse(text);self.assertEqual(len(rows),2)
        profiles,added,skipped=c.merge_profiles([],rows);self.assertEqual((len(added),skipped),(2,0))
        self.assertNotEqual(profiles[0]['id'],profiles[1]['id'])
        _,added,skipped=c.merge_profiles(profiles,rows);self.assertEqual((len(added),skipped),(0,2))

    def test_no_modules_commands_network_or_files_executed(self):
        # The extra call is syntax only; parsing must not execute any of it.
        with patch('os.system',side_effect=AssertionError('execution')),patch('subprocess.run',side_effect=AssertionError('execution')),patch('builtins.open',side_effect=AssertionError('file access')):
            self.parse(PY+'\nos.system("DO_NOT_EXECUTE")\n')
            self.parse(JS+'\nrequire("fs").readFileSync("DO_NOT_READ");')

    def test_dynamic_metadata_rejected(self):
        texts=[PY.replace('model="deepseek-v4-pro"','model=input()'),PY.replace('base_url="https://api.deepseek.com"','base_url=os.getenv("BASE_URL")'),
               JS.replace("model: 'deepseek-v4-pro'","model: getModel()"),JS.replace("baseURL: 'https://api.deepseek.com'","baseURL: 'https://' + host"),
               JS.replace("model: 'deepseek-v4-pro'","model: `deepseek-${version}`")]
        for text in texts:
            with self.subTest(text=text[:30]),self.assertRaises(ValueError):self.parse(text)

    def test_reassignment_and_object_mutation_rejected(self):
        for text in (PY+'\nclient.base_url="https://other.example"',PY+'\nclient=unknown()',JS+"\nclient.baseURL='https://other.example';",JS+'\nclient=unknown();'):
            with self.assertRaises(ValueError):self.parse(text)

    def test_import_and_parameter_shadowing_rejected(self):
        for text in (PY+'\ndef OpenAI():\n    pass',JS+'\nfunction OpenAI() {}',PY+'\ndef other(client):\n    pass',JS+'\nfunction other(client) {}'):
            with self.assertRaises(ValueError):self.parse(text)

    def test_cycles_and_deep_input_rejected(self):
        for text in ('from openai import OpenAI\nx=x\nc=OpenAI(base_url=x)\nc.responses.create(model="m")',"import OpenAI from 'openai';const x=x;const c=new OpenAI({baseURL:x});c.responses.create({model:'m'});",'from openai import OpenAI\nx='+ '['*300+'1'+']'*300):
            with self.assertRaises(ValueError):self.parse(text)

    def test_unknown_chat_hosts_are_not_converted(self):
        for text in (PY.replace('api.deepseek.com','api.other.example'),JS.replace('api.deepseek.com','api.deepseek.com.evil.example')):
            with self.assertRaisesRegex(ValueError,'尚未确认'):self.parse(text)

    def test_custom_headers_auth_and_query_rejected(self):
        for text in (PY.replace('base_url=', 'default_headers={"X":"FAKE_PRIVATE"},base_url='),JS.replace('baseURL:',"defaultHeaders:{'X':'FAKE_PRIVATE'},baseURL:"),PY.replace('model=', 'extra_headers={"X":"FAKE_PRIVATE"},model=')):
            with self.assertRaises(ValueError) as cm:self.parse(text)
            self.assertNotIn('FAKE_PRIVATE',str(cm.exception))

    def test_missing_request_and_invalid_syntax_preserve_secrets(self):
        for text in ('from openai import OpenAI\nc=OpenAI(api_key="FAKE_PRIVATE")',"import OpenAI from 'openai'; const c=new OpenAI({apiKey:'FAKE_PRIVATE'",PY.replace('model="deepseek-v4-pro"','model=') ):
            with self.assertRaises(ValueError) as cm:self.parse(text)
            self.assertNotIn('FAKE_PRIVATE',str(cm.exception))

    def test_metadata_duplicates_and_env_fallback_rejected(self):
        for text in (PY.replace('model="deepseek-v4-pro"','model="deepseek-v4-pro",model="other"'),JS.replace("model: 'deepseek-v4-pro'","model: 'deepseek-v4-pro',model:'other'"),PY.replace('os.environ.get("DEEPSEEK_API_KEY")','os.getenv("DEEPSEEK_API_KEY","fallback")')):
            with self.assertRaises(ValueError):self.parse(text)

    def test_reserved_env_and_invalid_effort_rejected(self):
        for text in (PY.replace('DEEPSEEK_API_KEY','PATH'),JS.replace('DEEPSEEK_API_KEY','PATH'),PY.replace('"high"','"invalid"'),JS.replace("'high'","'invalid'")):
            with self.assertRaises(ValueError):self.parse(text)

    def test_js_strings_comments_and_trailing_commas(self):
        self.parse(JS.replace("'deepseek-v4-pro'",'"deepseek-v4-pro"'))
        self.parse(JS.replace("'deepseek-v4-pro'",'`deepseek-v4-pro`'))
        rows,_=self.parse(JS.replace("'deepseek-v4-pro'",r"'deepseek-\u00764-pro'"));self.assertEqual(rows[0]['profile']['model'],'deepseek-v4-pro')
        self.parse(JS.replace('baseURL:', '/* literal metadata */ baseURL:'))

    def test_sdk_roundtrip_and_config_semantics(self):
        rows,_=self.parse(JS)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'p.json';c.save_profiles(p,[rows[0]['profile']])
            self.assertEqual(c.load_profiles(p),[rows[0]['profile']])
        cfg=tomllib.loads(c.render_config('[projects.demo]\ntrusted=true',rows[0]['profile']))
        self.assertEqual(cfg['model'],'deepseek-v4-pro');self.assertEqual(cfg['model_reasoning_effort'],'high')
        self.assertEqual(cfg['projects'],{'demo':{'trusted':True}})

    def test_toml_embedded_source_not_misdetected(self):
        text='model="demo"\nnotes="""\nimport os\n"""\n[model_providers.demo]\nbase_url="https://example.test"\nenv_key="DEMO_KEY"'
        rows,_=self.parse(text);self.assertEqual(rows[0]['profile']['model'],'demo')

    def test_arrow_function_wrapper(self):
        self.parse(JS.replace('async function main() {','const main = async () => {').replace('\n}\nmain();','\n};\nmain();'))

    def test_mutating_static_options_through_alias_rejected(self):
        for text in ('from openai import OpenAI\nopts={"base_url":"https://api.deepseek.com"}\nalias=opts\nalias.update({"base_url":"https://other.example"})\nc=OpenAI(**opts)\nc.responses.create(model="m")',
                     "import OpenAI from 'openai';const opts={baseURL:'https://api.deepseek.com'};const alias=opts;Object.assign(alias,{baseURL:'https://other.example'});const c=new OpenAI(opts);c.responses.create({model:'m'});"):
            with self.assertRaises(ValueError):self.parse(text)

    def test_unknown_import_overrides_and_loop_binding_rejected(self):
        for text in (PY+'\nfrom unknown import OpenAI',PY+'\nfor client in []:\n    pass',PY+'\ndel client'):
            with self.assertRaises(ValueError):self.parse(text)


if __name__=='__main__':unittest.main()
