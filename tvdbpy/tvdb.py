from __future__ import unicode_literals

import urlparse
import xml.etree.ElementTree as ET

from collections import defaultdict
from datetime import datetime

import requests

from tvdbpy.errors import (
    APIClientNotAvailableError,
    APIKeyRequiredError,
    APIResponseError,
)
from tvdbpy.helpers import BaseTvDB, api_key_required


class BaseSeries(BaseTvDB):
    """Minimum shared details for Series and SearchResult."""

    def __init__(self, xml_data, client=None):
        super(BaseSeries, self).__init__(client=client)
        self.id = self._elem_value(xml_data, 'id')
        self.imdb_id = self._elem_value(xml_data, 'IMDB_ID')
        self.name = self._elem_value(xml_data, 'SeriesName')
        self.overview = self._elem_value(xml_data, 'Overview')
        self.language = self._elem_value(xml_data, 'language')
        self._first_aired = self._elem_value(xml_data, 'FirstAired')
        self.network = self._elem_value(xml_data, 'Network')
        self._banner = self._elem_value(xml_data, 'banner')

    def __str__(self):
        return "Series: %s" % self.name

    @property
    def banner(self):
        """Return series banner url."""
        return urlparse.urljoin(self._base_image_url, self._banner)

    @property
    def first_aired(self):
        """Return series first aired date."""
        res = None
        if self._first_aired is not None:
            res = datetime.strptime(self._first_aired, "%Y-%m-%d").date()
        return res


class SearchResult(BaseSeries):
    """Series search result."""

    def get_series(self, full_record=False):
        if self._client is None:
            raise APIClientNotAvailableError("Missing TvDB client")
        return self._client.get_series_by_id(self.id, full_record=full_record)


class Series(BaseSeries):
    """Series details."""

    def __init__(self, xml_data, client=None):
        super(Series, self).__init__(xml_data, client=client)
        self.runtime = self._elem_value(xml_data, 'Runtime')
        self.status = self._elem_value(xml_data, 'Status')
        self._poster = self._elem_value(xml_data, 'poster')
        self.actors = self._elem_list_value(xml_data, 'Actors')
        self.genre = self._elem_list_value(xml_data, 'Genre')
        self._seasons = None

    def _load_episodes(self, data=None):
        # assert client is not None
        if data is None:
            data = self._client._get_series_full_data(self.id)
        episodes = self._client._parse_multiple_entries(data, Episode, './Episode')
        self._seasons = defaultdict(dict)
        for e in episodes:
            # need to set series into Episode
            e._series = self
            self._seasons[e.season][e.number] = e

    @property
    def poster(self):
        """Return series poster url."""
        return urlparse.urljoin(self._base_image_url, self._poster)

    @property
    def seasons(self):
        """Return all episodes details."""
        if self._seasons is None:
            self._load_episodes()
        return self._seasons

    def get_episode(self, season, number):
        """Return episode details."""
        if self._episodes:
            episode = self._seasons.get(season, {}).get(number)
        else:
            episode = self._client.get_episode(self.id, season, number)
        return episode


class Episode(BaseTvDB):
    """Episode details."""

    def __init__(self, xml_data, series=None, client=None):
        super(Episode, self).__init__(client=client)
        self._series = series
        self.id = self._elem_value(xml_data, 'id')
        self.imdb_id = self._elem_value(xml_data, 'IMDB_ID')
        self.series_id = self._elem_value(xml_data, 'seriesid')
        self.number = self._elem_value(xml_data, 'EpisodeNumber', cast=int)
        self.season = self._elem_value(xml_data, 'SeasonNumber', cast=int)
        self.name = self._elem_value(xml_data, 'EpisodeName')
        self.overview = self._elem_value(xml_data, 'Overview')
        self.guest_stars = self._elem_list_value(xml_data, 'GuestStars')
        self.director = self._elem_value(xml_data, 'Director')
        self.writer = self._elem_value(xml_data, 'Writer')
        self.language = self._elem_value(xml_data, 'Language')
        self._image = self._elem_value(xml_data, 'filename')
        self._first_aired = self._elem_value(xml_data, 'FirstAired')

    def __str__(self):
        return "Episode: %s" % self.name

    @property
    def series(self):
        """Return episode related series."""
        if self._series is None:
            self._series = self._client.get_series_by_id(self.series_id)
        return self._series

    @property
    def first_aired(self):
        """Return episode first aired date."""
        res = None
        if self._first_aired is not None:
            res = datetime.strptime(self._first_aired, "%Y-%m-%d").date()
        return res

    @property
    def image(self):
        """Return episode image url."""
        return urlparse.urljoin(self._base_image_url, self._image)


class TvDB(BaseTvDB):
    """TvDB API client."""

    def __init__(self, api_key=None):
        super(TvDB, self).__init__(client=None)
        self._api_key = api_key

    def _get_series_full_data(self, series_id):
        """Return full series XML data."""
        path = '%s/series/%s/all/en.zip' % (self._api_key, series_id)
        response = self._get_compressed_data(path)
        xml_file = response.read('en.xml')
        data = ET.fromstring(xml_file)
        return data

    def _parse_full_series(self, data):
        """Parse XML response and return expected cls instance(s)."""
        series = self._parse_entry(data, Series, './Series')
        if series:
            series._load_episodes(data)
        return series

    def search(self, title):
        """Search for series with the specified title."""
        response = self._get_xml_data('GetSeries.php', seriesname=title)
        return self._parse_multiple_entries(response, SearchResult, './Series')

    @api_key_required
    def get_series_by_id(self, series_id, full_record=False):
        """Get Series detail by series id."""
        if full_record:
            data = self._get_series_full_data(series_id)
            series = self._parse_full_series(data)
        else:
            path = '%s/series/%s/en.xml' % (self._api_key, series_id)
            response = self._get_xml_data(path)
            series = self._parse_entry(response, Series, './Series')
        return series

    @api_key_required
    def get_episode_by_id(self, episode_id):
        """Get Episode details by episode id."""
        path = '%s/episodes/%s/en.xml' % (self._api_key, episode_id)
        response = self._get_xml_data(path)
        return self._parse_entry(response, Episode, './Episode')

    @api_key_required
    def get_episode(self, series_id, season, number):
        """Get Episode details by season/number."""
        path = '%s/series/%s/default/%s/%s/en.xml' % (
            self._api_key, series_id, season, number)
        response = self._get_xml_data(path)
        return self._parse_entry(response, Episode, './Episode')
