import dataclasses
import os
import uuid

import rdflib.util
import requests
from urllib3.util import Retry
from requests.adapters import HTTPAdapter
import tempfile
import logging
import traceback
from time import time
from pp_api.models.models import PoolPartyProject

module_logger = logging.getLogger(__name__)


from pp_api import utils as _utils


class PoolParty:

    def __init__(self, server, auth_data=None, session=None, max_retries=None, timeout=None, lang="en", auth_type="basic_auth"):
        self.auth_data = auth_data
        if server.endswith("/"):
            server = server[:-1]
        self.server = server
        if auth_type == "basic_auth":
            self.session = _utils.get_session(session, auth_data)
        elif auth_type == "oauth2":
            self.session = _utils.get_oauth_session(session, auth_data)
        else:
            raise NotImplementedError
        if max_retries is not None:
            retries = Retry(total=max_retries,
                            backoff_factor=0.3,
                            status_forcelist=[500, 502, 503, 504])
            self.session.mount(self.server, HTTPAdapter(max_retries=retries))
        self.timeout = timeout
        self.lang=lang

    def extract(self, text, pid=None, lang=None, **kwargs):
        """
        Make extract call using project determined by pid.

        :param text: text
        :param pid: id of project
        :param lang: language

        Other parameters:
        :param auth_data:
        :param session:
        :param server: server url
        :param force_json If True, text is sent in the body of the post request in the "text" field of a json object.
                          otherwise, it is sent as part of a form-data POST request, in a field named "file".

        :return: response object
        """
        lang = self.lang if lang == None else lang
        tmp_file = tempfile.NamedTemporaryFile(delete=False, mode='w+b')
        tmp_file.write(str(text).encode('utf8'))
        tmp_file.seek(0)
        return self.extract_from_file(tmp_file, pid, lang=lang, **kwargs)

    def extract_from_file(self, file, pid, mb_time_factor=3, lang=None, force_json=False,
                          **kwargs):
        """
        Make extract call using project determined by pid.
        NOTE: Swallows all exceptions

        :param file: filename
        :param pid: id of project
        :param mb_time_factor: timeout scale factor (relative to file size)
        :param lang: language
        :return: response object
        """
        lang = self.lang if lang == None else lang
        data = {
            'numberOfConcepts': 100000,
            'numberOfTerms': 100000,
            'projectId': pid,
            'language': lang,
            'useTransitiveBroaderConcepts': True,
            'useRelatedConcepts': True,
            # 'sentimentAnalysis': True,
            'filterNestedConcepts': True,
            'showMatchingPosition': True,
            'showMatchingDetails': True
        }
        data.update(kwargs)
        target_url = self.server + '/extractor/api/extract'
        start = time()
        try:
            if not hasattr(file, 'read'):
                file = open(file, 'rb')
            file_text = file.read()
            # Findout filesize
            if self.timeout:
                countedTimeout = self.timeout
            else:
                file.seek(0, 2)  # Go to end of file
                f_size_mb = file.tell() / (1024 * 1024)
                file.seek(0)  # Go to start of file
                countedTimeout = (3.05, int(27 * mb_time_factor * (1 + f_size_mb)))

            if force_json:
                data['text'] = file_text
                r = self.session.post(
                    target_url,
                    data=data,
                    timeout=countedTimeout)
            else:
                r = self.session.post(
                    target_url,
                    data=data,
                    files={'file': file},
                    timeout=countedTimeout)
        except Exception as e:
            module_logger.error(traceback.format_exc())
        finally:
            file.close()
        module_logger.debug('call took {:0.3f}'.format(time() - start))

        if not 'r' in locals():
            return None
        self.raise_for_status(r)
        # try:
        #     r.raise_for_status()
        # except Exception as e:
        #     msg = 'JSON data of the failed POST request: {}\n'.format(data)
        #     msg += 'URL of the failed POST request: {}'.format(target_url)
        #     module_logger.error(msg)
        #     response = r.json()
        #     if "errorMessage" in response:
        #         extra = "API error message: {}\n".format(response["errorMessage"])
        #         raise type(e)(str(e) + "\n" + extra)
        #     else:
        #         raise e

        return r


    def raise_for_status(self, response, data=None):
        """
        Call the raise_for_status() method of the response, which will
        raise an HTTPError if an error response was received.
        But enrich it with information from our API, and also log
        the call parameters to module_logger.

        :param response: `requests` response object
        :param data: dictionary of call parameters, to include in log
        :return: None
        """
        _utils.check_status_and_raise(response, data=data, logger=module_logger)


    @staticmethod
    def get_cpts_from_response(r):
        # TODO: create a class ExtractedConcept
        attributes = ['prefLabel', 'prefLabels', 'frequencyInDocument', 'uri',
                      'score',
                      'transitiveBroaderConcepts', 'transitiveBroaderTopConcepts',
                      'relatedConcepts', 'conceptSchemes']
        # matchingLabels is checked and saved as well
        extr_cpts = []
        if r is None:
            return extr_cpts
        elif isinstance(r, requests.Response):
            concept_container = r.json()
        else:
            # Accept parsed json instead of the request object
            concept_container = r

        if not 'concepts' in concept_container:
            if not 'document' in concept_container:
                return extr_cpts
            if not 'concepts' in concept_container['document']:
                # no mention of concepts either in the json directly or document inside
                return extr_cpts
            else:
                # concepts are mentioned inside 'document'
                concept_container = concept_container['document']

        for cpt_json in concept_container['concepts']:
            cpt = dict()
            for attr in attributes:
                if attr in cpt_json:
                    cpt[attr] = cpt_json[attr]
                else:
                    cpt[attr] = []
            if 'matchingLabels' in cpt_json:
                cpt_matchings = []
                ms_labels = [(x['matchedTexts'], x['label'])
                             for x in cpt_json['matchingLabels']]

                for ms, label in ms_labels:
                    for m in ms:
                        cpt_matching = {
                            'lemma': label,
                            'text': m['matchedText'],
                            'frequency': m['frequency'],
                            'positions': [(x['beginningIndex'], x['endIndex']+1)
                                          for x in m['positions']]
                        }
                        cpt_matchings.append(cpt_matching)
                cpt['matchings'] = cpt_matchings
            extr_cpts.append(cpt)

        return extr_cpts

    def extract_shadow_cpts(self, text, shadow_cpts_corpus_id, pid, **kwargs):
        r = self.extract(
            text, pid, shadowConceptCorpusId=shadow_cpts_corpus_id, **kwargs
        )

        attributes = ['prefLabel', 'uri',
                      'transitiveBroaderConcepts', 'relatedConcepts',
                      'corporaScore']

        shadow_cpts = []
        if r is None:
            return shadow_cpts
        concept_container = r.json()

        if not 'shadowConcepts' in concept_container:
            if not 'document' in concept_container:
                return shadow_cpts
            if not 'shadowConcepts' in concept_container['document']:
                # no mention of concepts either in the json directly or document inside
                return shadow_cpts
            else:
                # concepts are mentioned inside 'document'
                concept_container = concept_container['document']

        for cpt_json in concept_container['shadowConcepts']:
            cpt = dict()
            for attr in attributes:
                if attr in cpt_json:
                    cpt[attr] = cpt_json[attr]
                else:
                    cpt[attr] = []
            shadow_cpts.append(cpt)

        return shadow_cpts, r

    @staticmethod
    def get_terms_from_response(r):
        attributes = ['textValue', 'frequencyInDocument', 'score']
        extr_terms = []
        if r is None:
            return extr_terms
        term_container = r.json()

        found = False
        for term_key_word in ['freeTerms', 'extractedTerms']:
            if term_key_word in term_container:
                found = True
                break
            elif 'document' in term_container and term_key_word in \
                    term_container['document']:
                term_container = term_container['document']
                found = True
                break

        if not found:
            module_logger.warning("No terms found in this document!")
            return extr_terms

        assert found, [extr_terms, list(term_container.keys()), r.json()]

        for term_json in term_container[term_key_word]:
            term = dict()
            for attr in attributes:
                if attr in term_json:
                    term[attr] = term_json[attr]
                else:
                    term[attr] = []
            extr_terms.append(term)

        return extr_terms

    @staticmethod
    def get_sentiment_from_response(r):
        return r.json()["sentiments"][0]["score"]

    @staticmethod
    def format_nif(text, cpts, doc_uri="http://example.doc/"+str(uuid.uuid4())):
        """
        Annotates a document with entities found in this objects thesaurus.
        The original document and the annotations are returned as NIF.

        :param text:
        :param cpts:
        :param doc_uri:
        :return: NIFDocument
        """
        try:
            from nif import NIFDocument
        except ImportError:
            raise ImportError("""To use format_nif(), install the nif module with\n
        pip install -e git+git://github.com/semantic-web-company/nif.git#egg=nif\n""")

        nif_doc = NIFDocument.from_text(text, uri=doc_uri)
        for cpt in cpts:
            nif_doc.add_extracted_cpt(cpt)
        return nif_doc

    def extract2nif(self, text, pid, lang='en',
                    doc_uri="http://example.doc/" + str(uuid.uuid4()),
                    **kwargs):

        r = self.extract(text, pid, lang=lang, force_json=True, **kwargs)
        cpts = self.get_cpts_from_response(r)
        return self.format_nif(text, cpts, doc_uri=doc_uri)

    def extract2nif_from_file(self, filename, **kwargs):
        if os.path.isfile(filename):
            with open(filename) as f:
                text = f.read()
            return self.extract2nif(text, **kwargs)

    def extract_nif(self, text, pid, lang=None,
                    include_terms=False, include_concepts=True,
                    prefix='doc.lynx-project.com'):
        target_url = self.server + '/extractor/api/annotate/nif'
        data = {
            'input': text,
            'prefix': prefix,
            'includeTerms': include_terms,
            'includeConcepts': include_concepts,
            'projectId': pid
        }
        if lang is not None:
            data['lang'] = lang
        r = self.session.post(
            target_url,
            data=data,
            timeout=self.timeout
        )
        r.raise_for_status()
        # self.raise_for_status(r, data)
        return r

    def get_pref_labels(self, uris, pid, lang=None):
        """
        Get prefLabels (in English) of all concepts specified by uris.

        :param uris:
        :param pid: id of project
        :return: response object
        """
        lang = self.lang if lang == None else lang
        data = {
            'concepts': uris,
            'projectId': pid,
            'language': lang,
        }
        target_url = self.server + '/PoolParty/api/thesaurus/{}/concepts'.format(pid)
        r = self.session.get(
            target_url,
            params=data,
            timeout=self.timeout
        )
        self.raise_for_status(r, data)
        return [x['prefLabel'] for x in r.json()]

    def get_cpts_info(self, uris, pid, lang=None):
        """
        Get all available info of concepts that PP returns

        :param uris:
        :param pid: id of project
        :return: response object
        """
        lang = self.lang if lang == None else lang
        data = {
            'concepts': uris,
            'language': lang,
            'properties': 'all'
        }
        target_url = self.server + '/PoolParty/api/thesaurus/{}/concepts'.format(pid)
        r = self.session.get(
            target_url,
            params=data,
            timeout=self.timeout
        )
        self.raise_for_status(r, data)
        return r.json()

    def get_cpt_corpus_freqs(self, corpus_id, pid):
        """
        Make call to PP to extract frequencies of concepts in a corpus.

        :param corpus_id: corpus id
        :param pid: id of project
        :return: response object
        """
        data = {
            'corpusId': corpus_id,
            'startIndex': 0
        }
        suffix = '/PoolParty/api/corpusmanagement/{pid}/results/concepts'.format(
            pid=pid
        )
        results = []
        while True:
            r = self.session.get(self.server + suffix, params=data, timeout=self.timeout)
            self.raise_for_status(r, data)
            data['startIndex'] += 20
            results += r.json()
            if not len(r.json()):
                break
        return results

    def get_cpt_path(self, cpt_uri, pid):
        """
        Make call to PP to extract path of concept.

        :param cpt_uri:
        :param pid: id of project
        :return: list: [(uri, label)] of cpt scheme and broaders
        """

        cpt_uri = str(cpt_uri)
        data = {
            'concept': cpt_uri
        }
        suffix = '/PoolParty/api/thesaurus/{pid}/getPaths'.format(
            pid=pid
        )
        target_url = self.server + suffix
        r = self.session.get(target_url, params=data, timeout=self.timeout)
        self.raise_for_status(r, data)

        broaders = [(x['uri'], x['prefLabel']) for x in
                    r.json()[0]['conceptPath']]
        cpt_scheme = r.json()[0]['conceptScheme']
        result = [(cpt_scheme['uri'], cpt_scheme['title'])] + broaders
        return result

    def get_term_coocs(self, term_str, corpus_id, pid):
        suffix = '/PoolParty/api/corpusmanagement/' \
                 '{pid}/results/cooccurrence/term'.format(
            pid=pid
        )
        data = {
            'corpusId': corpus_id,
            'term': term_str,
            'startIndex': 0,
            'limit': 2 ** 15,  # int(sys.maxsize)
        }
        results = []

        while True:
            r = self.session.get(self.server + suffix,
                            params=data,
                            timeout=self.timeout)
            self.raise_for_status(r, data)

            results += r.json()
            if len(r.json()) == 20:
                data['startIndex'] += len(r.json())
                if not len(r.json()):
                    break
            else:
                break

        return results

    def get_projects(self):
        suffix = '/PoolParty/api/projects'
        r = self.session.get(self.server + suffix, timeout=self.timeout)
        self.raise_for_status(r)
        result = r.json()
        return result

    def get_corpora(self, pid):
        suffix = '/PoolParty/api/corpusmanagement/{pid}/corpora'.format(pid=pid)
        r = self.session.get(self.server + suffix, timeout=self.timeout)
        self.raise_for_status(r)
        result = r.json()['jsonCorpusList']
        return result

    def get_corpus_documents(self, corpus_id, pid):
        suffix = '/PoolParty/api/corpusmanagement/{pid}/documents'.format(
            pid=pid)
        data = {
            'corpusId': corpus_id,
            'includeContent': True
        }
        r = self.session.get(self.server + suffix, params=data, timeout=self.timeout)
        self.raise_for_status(r, data)
        result = r.json()
        return result

    def get_document_terms(self, doc_id, corpus_id, pid):
        suffix = '/PoolParty/api/corpusmanagement/{pid}/documents/{docid}'.format(
            pid=pid, docid=doc_id
        )
        data = {
            'corpusId': corpus_id
        }
        r = self.session.get(self.server + suffix, params=data, timeout=self.timeout)
        self.raise_for_status(r, data)
        result = r.json()
        return result

    def get_allterms_scores(self, corpus_id, pid):
        suffix = '/PoolParty/api/corpusmanagement/{pid}/results/extractedterms'.format(
            pid=pid
        )
        data = {
            'corpusId': corpus_id,
            'startIndex': 0
        }
        results = []
        while True:
            r = self.session.get(self.server + suffix,
                                 params=data,
                                 timeout=self.timeout)
            self.raise_for_status(r, data)
            data['startIndex'] += 20
            results += r.json()
            if not len(r.json()):
                break
        return results

    def get_terms_stats(self, corpus_id, pid):
        suffix = '/PoolParty/api/corpusmanagement/{pid}/results/extractedterms'.format(
            pid=pid
        )
        data = {
            'corpusId': corpus_id,
            'startIndex': 0
        }
        results = []
        while True:
            r = self.session.get(self.server + suffix,
                                 params=data,
                                 timeout=self.timeout)
            self.raise_for_status(r, data)
            data['startIndex'] += 20
            results += r.json()
            if not len(r.json()):
                break
        return results

    def corpus_management_add_text(self, text, title, pid, corpusId, checkLanguage=True):
        suffix = '/PoolParty/api/corpusmanagement/{pid}/add'.format(
            pid=pid
        )
        target_url = self.server + suffix
        data = {
            'text': text,
            'title': title,
            'corpusId': corpusId,
            'checkLanguage': checkLanguage,
        }
        r = self.session.post(
            target_url,
            data=data,
            timeout=self.timeout
        )
        r.raise_for_status()
        return r

    def export_project(self, pid):
        suffix = '/PoolParty/api/projects/{pid}/export'.format(
            pid=pid
        )
        rdf_format = 'N3'
        data = {
            'format': rdf_format,
            'exportModules': ['concepts']
        }
        r = self.session.get(self.server + suffix, params=data, timeout=self.timeout)
        self.raise_for_status(r, data)
        return r.content

    def get_autocomplete(self, query_str, pid, lang='en'):
        suffix = '/extractor/api/suggest'
        data = {
            'projectId': pid,
            'searchString': query_str,
            'language': lang
        }
        r = self.session.get(self.server + suffix, params=data, timeout=self.timeout)
        self.raise_for_status(r, data)
        if r.json()['suggestedConcepts']:
            ans = [(x['prefLabel'], x['uri'])
                   for x in r.json()['suggestedConcepts']]
        else:
            ans = []
        return ans

    def get_onto(self, uri):
        suffix = '/PoolParty/api/schema/ontology'
        data = {
            'uri': uri
        }
        r = self.session.get(self.server + suffix, params=data, timeout=self.timeout)
        self.raise_for_status(r, data)
        ans = r.json()
        return ans

    def get_history(self, pid, from_=None):
        """

        :param pid: project
        :param from_: datetime instance or None
        :return:
        """
        suffix = '/PoolParty/api/history/{pid}'.format(
            pid=pid
        )
        data = dict()
        if from_ is not None:
            data.update({
                'fromTime': from_.strftime('%Y-%m-%dT%H:%M:%S')
            })
        r = self.session.get(self.server + suffix, params=data, timeout=self.timeout)
        self.raise_for_status(r, data)
        return r.json()

    def get_schemes(self, pid):
        suffix = '/PoolParty/api/thesaurus/{project}/schemes'.format(
            project=pid
        )
        r = self.session.get(self.server + suffix, timeout=self.timeout)
        self.raise_for_status(r)
        ans = r.json()
        return ans

    def add_new_concept(self, pid, pref_label, parent=None, suffix=None):
        """
        Add a new concept to the taxonomy (API call: createConcept)

        :param pid:
        :param pref_label: Preferred label in the default language
        :param parent: URI of the parent Concept Scheme or Concept
        :param suffix: When URI creation is manual, sets the last URI component.
        :return:
        """
        urlpath = '/PoolParty/api/thesaurus/{project}/createConcept'.format(
            project=pid
        )
        data = {
            'prefLabel': pref_label,
            'parent': (parent if parent is not None else
                       self.get_schemes(pid)[0]['uri'])
        }
        if suffix:
            data["suffix"] = suffix

        target_url = self.server + urlpath
        r = self.session.post(target_url, data=data, timeout=self.timeout)
        self.raise_for_status(r, data)
        ans = r.json()
        return ans

    def add_label(self, pid, uri, label_value,
                  label_type='skos:altLabel', lang=None):
        suffix = '/PoolParty/api/thesaurus/{project}/addLiteral'.format(
            project=pid
        )
        data = {
            'concept': uri,
            'label': label_value,
            'property': label_type,
            'language': lang
        }
        target_url = self.server + suffix
        r = self.session.post(target_url, data=data, timeout=self.timeout)
        self.raise_for_status(r, data)
        return r

    def add_relation(self, pid, source_uri, target_uri,
                     relation_type='skos:narrower'):
        suffix = '/PoolParty/api/thesaurus/{project}/addRelation'.format(
            project=pid
        )
        data = {
            'sourceConcept': source_uri,
            'targetConcept': target_uri,
            'property': relation_type,
        }
        target_url = self.server + suffix
        r = self.session.post(target_url, data=data, timeout=self.timeout)
        self.raise_for_status(r, data)
        return r

    def create_project_json(self, poolPartyProject : PoolPartyProject):
        suffix = "/PoolParty/api/projects/create"
        json = poolPartyProject.to_dict()
        target_url = self.server + suffix
        r = self.session.post(target_url, json=json, timeout=self.timeout)
        self.raise_for_status(r, json)
        return r

    def import_project(self, pid, triplesFilePath,  mimeType, defaultGraph=None, modules=None, overwrite=False):
        suffix = "/PoolParty/api/projects/{project}/import".format(project=pid)
        params = {
            "overwrite": overwrite
        }
        if modules is not None:
            params.update({"modules": modules})
        if defaultGraph is not None:
            params.update({"defaultGraph": defaultGraph})

        files = [
            ('file',
             (os.path.basename(triplesFilePath),
              open(triplesFilePath,'rb'),
              'application/octet-stream')
             )
        ]
        target_url = self.server + suffix
        r = self.session.post(target_url, params=params, files=files, timeout=self.timeout)
        self.raise_for_status(r)
        return r

    def delete_project(self, pid):
        suffix = "/PoolParty/api/projects/{project}/delete".format(project=pid)
        target_url = self.server + suffix
        headers = {'Content-type': 'application/x-www-form-urlencoded'}
        r = self.session.post(target_url, headers=headers, timeout=self.timeout)
        self.raise_for_status(r)
        return r

    def get_extraction_model_status(self, pid):
        suffix = "/PoolParty/api/indexbuilder/{project}".format(project=pid)
        target_url = self.server + suffix
        r = self.session.post(target_url, timeout=self.timeout)
        self.raise_for_status(r)
        return r

    def refresh_extraction_model(self, pid):
        suffix = "/PoolParty/api/indexbuilder/{project}/refresh".format(project=pid)
        target_url = self.server + suffix
        r = self.session.post(target_url, timeout=self.timeout)
        self.raise_for_status(r)
        return r

    def add_narrower(self, pid, broader_uri, narrower_uri):
        return self.add_relation(
            pid=pid, source_uri=broader_uri, target_uri=narrower_uri,
            relation_type='skos:narrower'
        )

    def add_related(self, pid, source_uri, target_uri):
        return self.add_relation(
            pid=pid, source_uri=source_uri, target_uri=target_uri,
            relation_type='skos:related'
        )

    def get_cpt_narrowers(self, pid, cpt_uri, transitive=True, lang=None):
        suffix = '/PoolParty/api/thesaurus/{project}/narrowers'.format(
            project=pid
        )
        data = {
            'concept': cpt_uri,
            'properties': 'all',
            'transitive': transitive,
        }
        if lang is not None:
            data['language'] = lang
        r = self.session.get(self.server + suffix, params=data, timeout=self.timeout)
        self.raise_for_status(r, data)
        ans = r.json()
        return ans

    def get_childconcepts(self, pid, parent,
                          properties=None, language=None, transitive=None, workflowStatus=None):
        """
        Implements the API call GET /thesaurus/{project}/childconcepts: Return
        children or descendants in the skos:narrower hierarchy

        :param pid:
        :param parent:
        :param properties:  None (default) | "all" | list of properties (URIs) to fetch
        :param language: Only Concept Schemes with labels in this locale will
                be displayed. If None (default), use the default locale of the project.
        :param transitive: If true, return all descendants; otherwise only children.
                Default: False.
        :param workflowStatus: Include workflow status information?
                Default: False
        :return:
        """

        suffix = '/PoolParty/api/thesaurus/{project}/childconcepts'.format(project=pid)
        data = dict(parent=parent)

        if properties == "all":
            data["properties"] = properties
        elif properties:
            data["properties"] = list(properties)
        # if None, simply leave it out

        if language:
            data["language"] = language
        if transitive:
            data["transitive"] = True
        if workflowStatus:
            data["workflowStates"] = True

        r = self.session.get(self.server + suffix, params=data, timeout=self.timeout)
        self.raise_for_status(r, data)
        result = r.json()
        return result

    def snapshot(self, pid, system=False, note=None, timeout=10):
        """
        Trigger a snapshot of the project specified by `pid`.

        :return: JSON structure with status report
        """
        suffix = '/PoolParty/api/projects/{project}/snapshot'.format(
            project=pid
        )

        data = { 'system': system }
        if note:
            data["note"] = note

        r = self.session.post(self.server + suffix, data=data, timeout=timeout)
        self.raise_for_status(r, data)
        result = r.json()
        return result

    def add_literal(self, pid, concept, property, label, language=None):
        """The api addLiteral call. Was already implemented under another name..."""

        return self.add_label(pid, concept, label_value=label,
                              label_type=property, language=language)

    def add_custom_attribute(self, pid, resource, property, value, language=None, datatype=None):

        urlpath = '/PoolParty/api/thesaurus/{project}/addCustomAttribute'.format(
            project=pid
        )
        data = {
            'resource': resource,
            'property': property,
            'value': value,
        }
        if language:
            data["language"] = language
        if datatype:
            data["datatype"] = datatype

        r = self.session.post(self.server + urlpath, data=data, timout=self.timeout)
        self.raise_for_status(r, data)
        return r

    def add_custom_relation(self, pid, source, property, target):

        urlpath = '/PoolParty/api/thesaurus/{project}/addCustomRelation'.format(
            project=pid
        )
        data = {
            'source': source,
            'property': property,
            'target': target,
        }
        r = self.session.post(self.server + urlpath, data=data, timeout=self.timeout)
        self.raise_for_status(r, data)
        return r


if __name__ == '__main__':
    pass
