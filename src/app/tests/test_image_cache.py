import gc
import json
import os
import tempfile
import time
from io import BytesIO
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.signals import request_started
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from PIL import Image
from rest_framework.request import Request

from api.renderers import ImageCacheJSONRenderer
from app import image_cache


def _png_bytes():
    output = BytesIO()
    Image.new("RGB", (2, 2), "red").save(output, format="PNG")
    return output.getvalue()


def _response(body, *, content_type="image/png", status_code=200, **headers):
    response = Mock()
    response.status_code = status_code
    response.headers = {"Content-Type": content_type, **headers}
    response.is_redirect = status_code in {301, 302, 303, 307, 308}
    response.is_permanent_redirect = status_code in {301, 308}
    response.iter_content.side_effect = lambda chunk_size: [body]
    response.close = Mock()
    return response


class ImageCacheServiceTests(TestCase):
    """Exercise URL policy, disk storage, endpoint headers, and cleanup."""

    def setUp(self):
        self.data_dir = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(FLOPPY_DATA_DIR=self.data_dir.name)
        self.settings_override.enable()
        image_cache.invalidate_setting_cache()
        image_cache.set_enabled(False)

    def tearDown(self):
        image_cache.invalidate_setting_cache()
        self.settings_override.disable()
        # Unconsumed FileResponses sit in reference cycles and keep their file
        # open until collected; Windows cannot delete an open file.
        gc.collect()
        self.data_dir.cleanup()

    def test_toggle_is_read_from_the_shared_cache_once_per_request(self):
        image_cache.set_enabled(True)
        url = "https://image.tmdb.org/t/p/w500/poster.jpg"
        request_started.send(sender=self.__class__)

        with patch.object(image_cache.cache, "get", wraps=cache.get) as cache_get:
            for _ in range(50):
                image_cache.rewrite_image_url(url)
            reads_in_request = cache_get.call_count
            request_started.send(sender=self.__class__)
            image_cache.rewrite_image_url(url)

        self.assertEqual(reads_in_request, 1)
        self.assertEqual(cache_get.call_count, 2)

    def test_approved_urls_rewrite_but_manual_and_local_urls_do_not(self):
        image_cache.set_enabled(True)
        request = RequestFactory().get("/api/v1/info/")
        approved = "https://image.tmdb.org/t/p/w500/poster.jpg?x=1"

        rewritten = image_cache.rewrite_image_url(approved, request=request)

        self.assertTrue(rewritten.startswith("http://testserver/image-cache/"))
        self.assertNotEqual(rewritten, approved)
        for value in (
            "",
            "data:image/png;base64,abc",
            "/static/img/placeholder.png",
            "https://example.com/manual.jpg",
            "http://127.0.0.1:8080/image.jpg",
            "http://audiobookshelf.local/image.jpg",
        ):
            self.assertEqual(image_cache.rewrite_image_url(value, request), value)

    def test_anonymous_miss_fetches_once_then_hit_returns_cache_headers(self):
        image_cache.set_enabled(True)
        source_url = "https://image.tmdb.org/t/p/original/poster.jpg"
        token = image_cache._token_for_url(source_url)
        body = _png_bytes()
        response = _response(body, **{"Content-Length": str(len(body))})

        with patch("app.image_cache.requests.get", return_value=response) as fetch:
            first = self.client.get(reverse("image_cache", kwargs={"token": token}))
            second = self.client.get(
                reverse("image_cache", kwargs={"token": token}),
                HTTP_IF_NONE_MATCH=first["ETag"],
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first["Content-Type"], "image/png")
        self.assertEqual(first["Content-Length"], str(len(body)))
        self.assertEqual(first["Cache-Control"], "public, max-age=86400")
        self.assertEqual(b"".join(first.streaming_content), body)
        self.assertEqual(second.status_code, 304)
        fetch.assert_called_once()
        self.assertEqual(image_cache.cache_stats()["count"], 1)

    def test_fanart_posters_and_backgrounds_are_shrunk_once_logos_are_not(self):
        image_cache.set_enabled(True)
        cases = {
            "https://assets.fanart.tv/fanart/the-matrix-5f8c1a2b3c4d5.jpg": ((1000, 1426), "JPEG", (500, 713)),
            "https://assets.fanart.tv/fanart/daredevil-5f8c1a2b3c4d6.jpg": ((1920, 1080), "JPEG", (1280, 720)),
            "https://assets.fanart.tv/fanart/daredevil-5f8c1a2b3c4d7.png": ((800, 310), "PNG", (800, 310)),
        }
        for url, (size, image_format, expected) in cases.items():
            output = BytesIO()
            Image.new("RGB", size, "red").save(output, format=image_format)
            body = output.getvalue()
            content_type = "image/jpeg" if image_format == "JPEG" else "image/png"
            token = image_cache._token_for_url(url)
            with patch("app.image_cache.requests.get", return_value=_response(body, content_type=content_type)):
                served = self.client.get(reverse("image_cache", kwargs={"token": token}))

            body = b"".join(served.streaming_content)
            served.close()
            with Image.open(BytesIO(body)) as image:
                self.assertEqual((image.size, image.format), (expected, image_format), url)

    def _cached_token(self):
        source_url = "https://image.tmdb.org/t/p/w342/poster.png"
        body = _png_bytes()
        image_cache.set_enabled(True)
        with patch(
            "app.image_cache.requests.get",
            return_value=_response(body, **{"Content-Length": str(len(body))}),
        ):
            self.assertTrue(image_cache._fetch_to_disk(source_url))
        return image_cache._token_for_url(source_url), image_cache._paths(source_url)[0]

    def test_behind_nginx_the_file_is_handed_over_with_its_type(self):
        token, data_path = self._cached_token()

        with override_settings(IMAGE_CACHE_ACCEL_REDIRECT="/_floppy-image-cache/"):
            response = self.client.get(reverse("image_cache", kwargs={"token": token}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Accel-Redirect"], f"/_floppy-image-cache/{data_path.name}")
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertIn("max-age=", response["Cache-Control"])
        self.assertEqual(response.content, b"")

    def test_without_nginx_django_sends_the_file(self):
        token, data_path = self._cached_token()

        response = self.client.get(reverse("image_cache", kwargs={"token": token}))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("X-Accel-Redirect", response)
        self.assertEqual(b"".join(response.streaming_content), data_path.read_bytes())

    def test_poster_requests_skip_the_session_and_user_lookups(self):
        token, _data_path = self._cached_token()
        user = get_user_model().objects.create_user(username="poster-viewer", password="x" * 12)
        self.client.force_login(user)
        url = reverse("image_cache", kwargs={"token": token})

        with self.assertNumQueries(0), patch(
            "app.middleware.mark_interactive_request",
        ) as mark_active:
            response = self.client.get(url, HTTP_ACCEPT="image/avif,image/webp,*/*")

        self.assertEqual(response.status_code, 200)
        mark_active.assert_not_called()

    def test_disabled_cache_serves_existing_files_but_does_not_download(self):
        source_url = "https://image.tmdb.org/t/p/original/poster.jpg"
        token = image_cache._token_for_url(source_url)
        body = _png_bytes()
        image_cache.set_enabled(True)
        with patch(
            "app.image_cache.requests.get",
            return_value=_response(body, **{"Content-Length": str(len(body))}),
        ):
            self.assertEqual(
                self.client.get(reverse("image_cache", kwargs={"token": token})).status_code,
                200,
            )

        image_cache.set_enabled(False)
        with patch("app.image_cache.requests.get") as fetch:
            self.assertEqual(
                self.client.get(reverse("image_cache", kwargs={"token": token})).status_code,
                200,
            )
            missing_token = image_cache._token_for_url(
                "https://image.tmdb.org/t/p/original/missing.jpg",
            )
            self.assertEqual(
                self.client.get(
                    reverse("image_cache", kwargs={"token": missing_token}),
                ).status_code,
                404,
            )
        fetch.assert_not_called()

    def test_tampering_unknown_hosts_redirects_and_non_images_are_rejected(self):
        image_cache.set_enabled(True)
        valid_token = image_cache._token_for_url(
            "https://image.tmdb.org/t/p/original/valid.jpg",
        )
        tampered_token = f"{valid_token[:-1]}x"
        self.assertEqual(
            self.client.get(reverse("image_cache", kwargs={"token": tampered_token})).status_code,
            404,
        )
        unknown_token = image_cache._token_for_url("https://example.com/image.jpg")
        self.assertEqual(
            self.client.get(reverse("image_cache", kwargs={"token": unknown_token})).status_code,
            404,
        )

        source_url = "https://image.tmdb.org/t/p/original/unsafe.jpg"
        token = image_cache._token_for_url(source_url)
        redirect = _response(
            b"",
            status_code=302,
            **{"Location": "http://127.0.0.1/private", "Content-Type": "text/plain"},
        )
        with patch("app.image_cache.requests.get", return_value=redirect) as fetch:
            self.assertEqual(
                self.client.get(reverse("image_cache", kwargs={"token": token})).status_code,
                404,
            )
        fetch.assert_called_once()

        non_image = _response(b"not an image", content_type="text/html")
        with patch("app.image_cache.requests.get", return_value=non_image):
            self.assertEqual(
                self.client.get(reverse("image_cache", kwargs={"token": token})).status_code,
                404,
            )

    def test_revalidation_refetches_expired_copies_and_drops_legacy_ones(self):
        image_cache.set_enabled(True)
        image_cache.set_retention_days(7)
        self.addCleanup(cache.delete, image_cache.RETENTION_CACHE_KEY)
        urls = [f"https://image.tmdb.org/t/p/original/{name}.jpg" for name in ("expired", "fresh", "legacy")]
        with patch("app.image_cache.requests.get", side_effect=lambda *a, **k: _response(_png_bytes())):
            for url in urls:
                self.assertTrue(image_cache._fetch_to_disk(url))
        expired_metadata = image_cache._paths(urls[0])[1]
        metadata = json.loads(expired_metadata.read_text())
        self.assertEqual(metadata["url"], urls[0])
        metadata["fetched_at"] = time.time() - 8 * image_cache.DAY_SECONDS
        expired_metadata.write_text(json.dumps(metadata))
        legacy_data, legacy_metadata = image_cache._paths(urls[2])
        legacy_metadata.write_text(json.dumps({"content_type": "image/png", "etag": '"x"'}))

        with patch("app.image_cache.requests.get", return_value=_response(_png_bytes())) as fetch:
            summary = image_cache.revalidate_images()

        self.assertEqual(summary, {"refreshed": 1, "dropped": 1, "failed": 0})
        self.assertEqual(fetch.call_args.args[0], urls[0])
        self.assertGreater(json.loads(expired_metadata.read_text())["fetched_at"], time.time() - 60)
        self.assertFalse(legacy_data.exists())

    def test_cleanup_removes_old_entries_and_preserves_recent_entries(self):
        image_cache.set_enabled(True)
        body = _png_bytes()
        urls = [
            "https://image.tmdb.org/t/p/original/old.jpg",
            "https://image.tmdb.org/t/p/original/recent.jpg",
        ]
        with patch(
            "app.image_cache.requests.get",
            side_effect=[
                _response(body, **{"Content-Length": str(len(body))}),
                _response(body, **{"Content-Length": str(len(body))}),
            ],
        ):
            for url in urls:
                # Close the streamed FileResponse, as Django's handler does;
                # an open handle blocks the cleanup's unlink on Windows.
                self.client.get(
                    reverse(
                        "image_cache",
                        kwargs={"token": image_cache._token_for_url(url)},
                    ),
                ).close()

        old_data, old_metadata = image_cache._paths(urls[0])
        old_time = time.time() - image_cache.DEFAULT_RETENTION_DAYS * image_cache.DAY_SECONDS - 1
        os.utime(old_data, (old_time, old_time))
        os.utime(old_metadata, (old_time, old_time))

        summary = image_cache.cleanup_stale_images()

        self.assertEqual(summary["removed_count"], 1)
        self.assertGreater(summary["removed_bytes"], 0)
        self.assertFalse(old_data.exists())
        self.assertTrue(image_cache._paths(urls[1])[0].exists())

    def test_a_view_keeps_the_poster_file_time_and_counts_as_use(self):
        url = "https://image.tmdb.org/t/p/w500/kept.jpg"
        image_cache.set_enabled(True)
        body = _png_bytes()
        with patch(
            "app.image_cache.requests.get",
            return_value=_response(body, **{"Content-Length": str(len(body))}),
        ):
            self.client.get(
                reverse("image_cache", kwargs={"token": image_cache._token_for_url(url)}),
            ).close()
        data_path, metadata_path = image_cache._paths(url)
        old_time = time.time() - image_cache.DEFAULT_RETENTION_DAYS * image_cache.DAY_SECONDS - 1
        os.utime(data_path, (old_time, old_time))
        os.utime(metadata_path, (old_time, old_time))

        self.client.get(
            reverse("image_cache", kwargs={"token": image_cache._token_for_url(url)}),
        ).close()

        # nginx's ETag comes from this time, so it must not move on a view.
        self.assertEqual(data_path.stat().st_mtime, old_time)
        self.assertEqual(image_cache.cleanup_stale_images()["removed_count"], 0)
        self.assertTrue(data_path.exists())

    def test_api_renderer_rewrites_image_fields_without_changing_shape(self):
        image_cache.set_enabled(True)
        request = Request(RequestFactory().get("/api/v1/info/"))
        payload = {
            "image": "https://image.tmdb.org/t/p/w500/poster.jpg",
            "nested": [{"image_url": "https://example.com/manual.jpg"}],
        }

        rendered = ImageCacheJSONRenderer().render(
            payload,
            renderer_context={"request": request},
        )
        result = json.loads(rendered)

        self.assertTrue(result["image"].startswith("http://testserver/image-cache/"))
        self.assertEqual(result["nested"][0]["image_url"], "https://example.com/manual.jpg")
        self.assertEqual(set(result), set(payload))


def _image_bytes(size, image_format, mode="RGB"):
    output = BytesIO()
    color = (200, 30, 30, 128) if mode == "RGBA" else "red"
    Image.new(mode, size, color).save(output, format=image_format)
    return output.getvalue()


class ImageVariantTests(TestCase):
    """Card-size copies of cached originals (v2 P2-C)."""

    TVDB_URL = "https://artworks.thetvdb.com/banners/posters/81189-1.jpg"

    def setUp(self):
        self.data_dir = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(FLOPPY_DATA_DIR=self.data_dir.name)
        self.settings_override.enable()
        image_cache.invalidate_setting_cache()
        image_cache.set_enabled(True)
        request_started.send(sender=self.__class__)

    def tearDown(self):
        image_cache.invalidate_setting_cache()
        self.settings_override.disable()
        gc.collect()
        self.data_dir.cleanup()

    def _cache(self, url, size=(680, 1000), image_format="JPEG", mode="RGB"):
        body = _image_bytes(size, image_format, mode)
        content_type = {"JPEG": "image/jpeg", "PNG": "image/png", "GIF": "image/gif"}[image_format]
        with patch(
            "app.image_cache.requests.get",
            return_value=_response(body, content_type=content_type),
        ):
            self.assertTrue(image_cache._fetch_to_disk(url))
        request_started.send(sender=self.__class__)
        return image_cache._paths(url)

    def _get(self, url, **query):
        path = reverse("image_cache", kwargs={"token": image_cache._token_for_url(url)})
        response = self.client.get(path, query)
        body = b"".join(response.streaming_content) if response.streaming else response.content
        response.close()
        return response, body

    def _version(self, url):
        data_path, metadata_path = image_cache._paths(url)
        return image_cache._version(image_cache._metadata(data_path, metadata_path))

    def test_a_card_width_gets_a_smaller_copy_named_after_the_content_hash(self):
        data_path, _ = self._cache(self.TVDB_URL)
        version = self._version(self.TVDB_URL)

        first, body = self._get(self.TVDB_URL, w=342)
        variant = data_path.with_name(f"{data_path.stem}.{version}.w342.img")
        made_at = variant.stat().st_mtime
        second, _ = self._get(self.TVDB_URL, w=342)

        with Image.open(BytesIO(body)) as image:
            self.assertEqual((image.size, image.format), ((342, 503), "JPEG"))
        self.assertEqual(first["Content-Type"], "image/jpeg")
        self.assertEqual(first["ETag"], f'"{version}-w342"')
        self.assertEqual(variant.stat().st_mtime, made_at)
        self.assertEqual(second.status_code, 200)
        original, _ = self._get(self.TVDB_URL)
        self.assertNotEqual(original["ETag"], first["ETag"])

    def test_transparent_png_stays_a_transparent_png(self):
        url = "https://artworks.thetvdb.com/banners/posters/alpha.png"
        self._cache(url, size=(800, 1200), image_format="PNG", mode="RGBA")

        _, body = self._get(url, w=185)

        with Image.open(BytesIO(body)) as image:
            self.assertEqual((image.size, image.format, image.mode), ((185, 278), "PNG", "RGBA"))

    def test_narrow_originals_unknown_widths_and_gifs_get_the_original(self):
        mal = "https://cdn.myanimelist.net/images/anime/1/1.jpg"
        gif = "https://artworks.thetvdb.com/banners/posters/moving.gif"
        mal_data, _ = self._cache(mal, size=(225, 320))
        self._cache(self.TVDB_URL)
        gif_data, _ = self._cache(gif, size=(600, 900), image_format="GIF")

        _, narrow = self._get(mal, w=342)
        _, unknown = self._get(self.TVDB_URL, w=999)
        _, moving = self._get(gif, w=342)

        self.assertEqual(narrow, mal_data.read_bytes())
        self.assertEqual(unknown, image_cache._paths(self.TVDB_URL)[0].read_bytes())
        self.assertEqual(moving, gif_data.read_bytes())
        self.assertEqual(list(mal_data.parent.glob("*.img")), [])

    def test_the_page_url_names_the_version_and_only_that_is_immutable(self):
        self.assertEqual(
            image_cache.rewrite_image_url(self.TVDB_URL, width=342),
            reverse("image_cache", kwargs={"token": image_cache._token_for_url(self.TVDB_URL)})
            + "?w=342",
        )
        self._cache(self.TVDB_URL)
        version = self._version(self.TVDB_URL)

        rendered = image_cache.rewrite_image_url(self.TVDB_URL, width=342)
        current, _ = self._get(self.TVDB_URL, w=342, v=version)
        stale, _ = self._get(self.TVDB_URL, w=342, v="0" * 16 + "-1")

        self.assertTrue(rendered.endswith(f"?w=342&v={version}"))
        self.assertEqual(
            current["Cache-Control"],
            f"public, max-age={image_cache.IMMUTABLE_MAX_AGE_SECONDS}, immutable",
        )
        self.assertEqual(stale["Cache-Control"], "public, max-age=86400")

    def test_a_failed_resize_sends_the_original_without_immutable(self):
        data_path, _ = self._cache(self.TVDB_URL)
        version = self._version(self.TVDB_URL)

        with patch("app.image_cache._ensure_variant", side_effect=OSError("disk full")):
            response, body = self._get(self.TVDB_URL, w=342, v=version)

        self.assertEqual(body, data_path.read_bytes())
        self.assertEqual(response["Cache-Control"], "public, max-age=86400")

    def test_behind_nginx_the_copy_is_handed_over(self):
        data_path, _ = self._cache(self.TVDB_URL)
        version = self._version(self.TVDB_URL)

        with override_settings(IMAGE_CACHE_ACCEL_REDIRECT="/_floppy-image-cache/"):
            response, _ = self._get(self.TVDB_URL, w=154)

        self.assertEqual(
            response["X-Accel-Redirect"],
            f"/_floppy-image-cache/{data_path.stem}.{version}.w154.img",
        )

    def test_without_a_width_urls_and_api_payloads_are_unchanged(self):
        self._cache(self.TVDB_URL)
        plain = image_cache.rewrite_image_url(self.TVDB_URL)
        payload = image_cache.rewrite_payload_images({"image": self.TVDB_URL})

        self.assertNotIn("?", plain)
        self.assertEqual(payload, {"image": plain})
        image_cache.set_enabled(False)
        self.assertEqual(image_cache.rewrite_image_url(self.TVDB_URL, width=342), self.TVDB_URL)

    def test_rendering_counts_as_use_at_most_once_a_day(self):
        _, metadata_path = self._cache(self.TVDB_URL)
        old_time = time.time() - image_cache.DEFAULT_RETENTION_DAYS * image_cache.DAY_SECONDS - 1
        os.utime(metadata_path, (old_time, old_time))

        image_cache.rewrite_image_url(self.TVDB_URL, width=342)
        touched = metadata_path.stat().st_mtime
        request_started.send(sender=self.__class__)
        image_cache.rewrite_image_url(self.TVDB_URL, width=185)

        self.assertGreater(touched, old_time)
        self.assertEqual(metadata_path.stat().st_mtime, touched)
        self.assertEqual(image_cache.cleanup_stale_images()["removed_count"], 0)

    def test_copies_of_a_changed_or_removed_original_are_cleaned_up(self):
        data_path, metadata_path = self._cache(self.TVDB_URL)
        self._get(self.TVDB_URL, w=342)
        self._get(self.TVDB_URL, w=185)
        stats = image_cache.cache_stats()
        self.assertEqual(stats["count"], 1)
        self.assertGreater(
            stats["bytes"],
            data_path.stat().st_size + metadata_path.stat().st_size,
        )

        # The nightly refetch found new art: the old copies are no use.
        self._cache(self.TVDB_URL, size=(700, 1000))
        self._get(self.TVDB_URL, w=342)
        image_cache.cleanup_stale_images()
        version = self._version(self.TVDB_URL)
        self.assertEqual(
            sorted(path.name for path in data_path.parent.glob("*.img")),
            [f"{data_path.stem}.{version}.w342.img"],
        )

        summary = image_cache.clear_cache()
        self.assertEqual(summary["removed_count"], 1)
        self.assertEqual(list(data_path.parent.iterdir()), [])


class CardImageFilterTests(TestCase):
    """tmdb_size, image_url and tmdb_srcset ask the cache for card sizes."""

    def setUp(self):
        self.data_dir = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(FLOPPY_DATA_DIR=self.data_dir.name)
        self.settings_override.enable()
        image_cache.invalidate_setting_cache()
        image_cache.set_enabled(True)
        request_started.send(sender=self.__class__)

    def tearDown(self):
        image_cache.invalidate_setting_cache()
        self.settings_override.disable()
        self.data_dir.cleanup()

    def test_other_providers_get_the_width_and_tmdb_keeps_its_own_sizes(self):
        from app.templatetags import app_tags

        fanart = "https://assets.fanart.tv/fanart/movie-poster-1.jpg"
        tmdb = "https://image.tmdb.org/t/p/w500/poster.jpg"

        self.assertTrue(app_tags.image_url(app_tags.tmdb_size(fanart, "w342")).endswith("?w=342"))
        self.assertNotIn("?", app_tags.image_url(app_tags.tmdb_size(tmdb, "w342")))
        self.assertEqual(app_tags.tmdb_size(fanart, "w342"), fanart)
        srcset = app_tags.tmdb_srcset(fanart, "w185,w342")
        self.assertRegex(srcset, r"^/image-cache/\S+\?w=185 185w, /image-cache/\S+\?w=342 342w$")
        tmdb_srcset = app_tags.tmdb_srcset(tmdb)
        self.assertIn(" 185w, ", tmdb_srcset)
        self.assertNotIn("?w=", tmdb_srcset)
        self.assertEqual(app_tags.tmdb_srcset("https://example.com/manual.jpg"), "")

        image_cache.set_enabled(False)
        self.assertEqual(app_tags.tmdb_srcset(fanart), "")
        self.assertEqual(app_tags.image_url(app_tags.tmdb_size(fanart, "w342")), fanart)
