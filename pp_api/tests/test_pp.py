import os
from pathlib import Path

from decouple import config

from pp_api import *


class TestPP():
    def setUp(self):
        this_dir = Path(__file__).parent
        self.data_folder = this_dir / 'data'
        auth_data = tuple(map(lambda x: config(x),
                              ['pp_user', 'pp_password']))
        assert auth_data[0] and auth_data[1]
        self.pp = PoolParty(server=config('server'), auth_data=auth_data)
        self.extract_args = {
            'sparql_endpoint': config('sparql_endpoint'),
            'pid': config('chebi_pid')
        }

    def setUpOAuth(self):
        this_dir = Path(__file__).parent
        self.data_folder = this_dir / 'data'
        self.pp = PoolParty(server=config('server'), auth_type="oauth2")

    def do_extract(self, text_path):
        r = self.pp.extract_from_file(
            text_path.open(), **self.extract_args
        )
        terms = pp_api.PoolParty.get_terms_from_response(r)
        # print(r.json())
        assert(terms)

    def test_sigma_pi(self):
        path = self.data_folder / 'question_1727.txt'
        self.do_extract(path)

    def test_illegal_char_sentiment(self):
        path = self.data_folder / 'question_2189.txt'
        self.do_extract(path)

    def test_small_question(self):
        path = self.data_folder / 'question_921.txt'
        self.do_extract(path)

    def test_nif_annotation(self):
        text_path = (self.data_folder / 'question_1727.txt')
        with text_path.open() as f:
            text = f.read()
        nif_output = self.pp.extract2nif(text=text,
                                         pid=self.extract_args['pid'])
        print(nif_output)
        assert len(nif_output.split("nif:Phrase")) > 0

    def test_ppnif_annotation(self):
        text_path = (self.data_folder / 'question_1727.txt')
        with text_path.open() as f:
            text = f.read()
        nif_output = self.pp.extract_nif(text=text,
                                         pid=self.extract_args['pid'])
        print(nif_output)
        assert len(nif_output.split("nif:Phrase")) > 0

    def test_shadow_cpts_extraction(self):
        text_path = (self.data_folder / 'question_1727.txt')
        self.extract_args.update({
            'shadow_cpts_corpus_id': config('chebi_corpus_id')
        })
        with text_path.open() as f:
            text = f.read()
        scpts, r = self.pp.extract_shadow_cpts(
            text,
            **self.extract_args
        )
        assert hasattr(scpts, '__len__')
        assert len(scpts) > 0

    def test_create_project(self):
        poolPartyProject = PoolPartyProject("en", "Test Project", ["Public"], repositoryType="memory")
        result = self.pp.create_project_json(poolPartyProject)
        self.projectId = result.json()["id"]
        assert result.status_code == 201

    def test_import_project_data(self):
        triples_file_path = ( self.data_folder / 'minimal_taxonomy.ttl')
        result = self.pp.import_project(self.projectId, triples_file_path, "text/turtle", defaultGraph="concepts")
        assert result.status_code == 200

    def test_refresh_extraction_model(self):
        result = self.pp.refresh_extraction_model(self.projectId)
        assert result.status_code == 200
        assert result.json()["success"] == True

    def test_delete_project(self):
        result = self.pp.delete_project(self.projectId)
        assert result.status_code == 200