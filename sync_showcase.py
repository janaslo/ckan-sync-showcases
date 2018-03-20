
import argparse
import os
import re
import requests
import sys

from ckanapi import RemoteCKAN, NotFound


class ShowcaseMetadata(dict):
    """Copy of CKAN shocase dict containing only non-internal attributes
    and with sorted extras and tags lists. That allows simple comparison
    with other instances.
    """
    def __init__(self, showcase_meta_dict):
        super().__init__()
        keys = [
            'author',
            'author_email',
            'name',
            'notes',
            'state',
            'title',
            'type',
            'url',
        ]
        self.update({k: showcase_meta_dict.get(k) for k in keys})
        tags = [
            {k: td.get(k) for k in ['display_name', 'name', 'state']}
            for td in showcase_meta_dict.get('tags', [])]
        #self.update({
        #    'tags': sorted(tags, key=lambda x: x['display_name']),
        #})
        self._image_url = showcase_meta_dict.get('image_display_url')
        if self._image_url:
            full_image_name = os.path.basename(self._image_url)
            self._image_name = re.sub(r'^[\d-]+\.\d{6}', '', full_image_name)
        else:
            self._image_name = ''


class ShowcaseUpdater:
    def __init__(self, source_repo, target_repo, tmp_dir):
        self.source_repo = source_repo
        self.target_repo = target_repo
        self.tmp_dir = tmp_dir

    def sync_showcases(self):
        source_names = [
            sc['name'] for sc in self.source_repo.action.ckanext_showcase_list()]
        for sc_name in source_names:
            source_sc = self.source_repo.action.ckanext_showcase_show(
                id=sc_name)
            source_sc_meta = ShowcaseMetadata(source_sc)
            try:
                target_sc = self.target_repo.action.ckanext_showcase_show(
                    id=sc_name)
            except NotFound:     # showcase not found -> create it
                image_dict = self.prepare_image_dict(
                    source_sc_meta._image_url, source_sc_meta._image_name)
                source_sc_meta.update(image_dict)
                self.target_repo.action.ckanext_showcase_create(**source_sc_meta)
            else:       # showcase found -> compare (and update metadata)
                target_sc_meta = ShowcaseMetadata(target_sc)
                needs_update = (source_sc_meta != target_sc_meta or
                    source_sc_meta._image_name != target_sc_meta._image_name)
                if needs_update:
                    image_dict = self.prepare_image_dict(
                        source_sc_meta._image_url, source_sc_meta._image_name)
                    source_sc_meta.update(image_dict)
                    self.target_repo.action.ckanext_showcase_update(**source_sc_meta)
            self.sync_datasets(sc_name)
    
    def prepare_image_dict(self, image_url, image_name):
        image_dict = {'image_url': ''}
        if image_url.startswith(self.source_repo.address):
            image_file = self.download_file(image_url, image_name)
            image_dict['image_upload'] = open(image_file, 'rb')
        else:   # external image
            image_dict['image_url'] = image_url
        return image_dict


    def download_file(self, url, filename):
        location = os.path.join(self.tmp_dir, filename)
        r = requests.get(url)
        with open(location, 'wb') as fd:
            for chunk in r.iter_content(4096):
                fd.write(chunk)
        return location

    def sync_datasets(self, showcase_name):
        def get_dataset_list(repo, showcase_name):
            return [
                package['name'] for package in
                repo.action.ckanext_showcase_package_list(
                    showcase_id=showcase_name)]

        source_datasets = get_dataset_list(self.source_repo, showcase_name)
        target_datasets = get_dataset_list(self.target_repo, showcase_name)

        for dataset in source_datasets:
            if dataset not in target_datasets:
                self.target_repo.action.ckanext_showcase_package_association_create(
                        showcase_id=showcase_name, package_id=dataset)

        for dataset in target_datasets:
            if dataset not in source_datasets:
                self.target_repo.action.ckanext_showcase_package_association_delete(
                        showcase_id=showcase_name, package_id=dataset)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='CKAN showcases synchronization')
    parser.add_argument('--source', help='source repo URL')
    parser.add_argument('--target', help='target repo URL')
    parser.add_argument('--target-key', help='target API key')
    parser.add_argument('--tmp-dir', help='tmp dir for images', default='/tmp/')

    args = parser.parse_args()
    if not all(vars(args).values()):
        parser.print_help()
        sys.exit(1)

    source_repo = RemoteCKAN(args.source)
    target_repo = RemoteCKAN(args.target, args.target_key)
    updater = ShowcaseUpdater(source_repo, target_repo, args.tmp_dir)
    updater.sync_showcases()
