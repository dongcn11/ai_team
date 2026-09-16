"""Test API tạo khóa học."""
from fastapi.testclient import TestClient

VALID = {
    "title": "Luyện thi IELTS 6.5 cấp tốc",
    "level": "band_6_5",
    "skill": "full",
    "target_band": 6.5,
    "duration_weeks": 8,
    "sessions_per_week": 3,
    "price_vnd": 12_000_000,
    "max_students": 16,
}


def _payload(**over):
    return {**VALID, **over}


def test_tao_khoa_hoc_toi_thieu(client: TestClient):
    r = client.post("/api/courses", json=_payload())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] > 0
    assert body["slug"] == "luyen-thi-ielts-6-5-cap-toc"   # bỏ dấu tiếng Việt
    assert body["status"] == "draft"                        # mặc định là bản nháp
    assert body["total_sessions"] == 24                     # 8 tuần x 3 buổi
    assert body["created_at"]


def test_slug_trung_ten_duoc_them_hau_to(client: TestClient):
    first = client.post("/api/courses", json=_payload()).json()
    second = client.post("/api/courses", json=_payload()).json()
    assert second["slug"] == f"{first['slug']}-2"


def test_slug_nhap_tay_bi_trung_thi_409(client: TestClient):
    client.post("/api/courses", json=_payload(slug="ielts-cap-toc"))
    r = client.post("/api/courses", json=_payload(title="Khóa khác", slug="ielts-cap-toc"))
    assert r.status_code == 409
    assert "ielts-cap-toc" in r.json()["detail"]


def test_slug_sai_dinh_dang_bi_tu_choi(client: TestClient):
    r = client.post("/api/courses", json=_payload(slug="Khóa Học!"))
    assert r.status_code == 422


def test_published_bat_buoc_co_ngay_khai_giang(client: TestClient):
    r = client.post("/api/courses", json=_payload(status="published"))
    assert r.status_code == 422
    assert "khai giảng" in r.text

    ok = client.post(
        "/api/courses",
        json=_payload(status="published", start_date="2026-09-15", slug="ielts-thang-9"),
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["start_date"] == "2026-09-15"


def test_published_bat_buoc_co_hoc_phi(client: TestClient):
    r = client.post(
        "/api/courses",
        json=_payload(status="published", start_date="2026-09-15", price_vnd=0),
    )
    assert r.status_code == 422
    assert "học phí" in r.text


def test_band_phai_la_boi_cua_nua_diem(client: TestClient):
    assert client.post("/api/courses", json=_payload(target_band=6.3)).status_code == 422
    assert client.post("/api/courses", json=_payload(target_band=10)).status_code == 422
    assert client.post("/api/courses", json=_payload(target_band=7.0)).status_code == 201


def test_ten_qua_ngan_bi_tu_choi(client: TestClient):
    assert client.post("/api/courses", json=_payload(title="AB")).status_code == 422
    # đủ dài trước khi gom khoảng trắng, quá ngắn sau khi gom
    assert client.post("/api/courses", json=_payload(title="A     ")).status_code == 422


def test_ten_duoc_gom_khoang_trang_thua(client: TestClient):
    body = client.post("/api/courses", json=_payload(title="  IELTS   Writing  ")).json()
    assert body["title"] == "IELTS Writing"


def test_level_sai_bi_tu_choi(client: TestClient):
    assert client.post("/api/courses", json=_payload(level="band_9_9")).status_code == 422


def test_gia_va_si_so_ngoai_khoang(client: TestClient):
    assert client.post("/api/courses", json=_payload(price_vnd=-1)).status_code == 422
    assert client.post("/api/courses", json=_payload(max_students=0)).status_code == 422
    assert client.post("/api/courses", json=_payload(duration_weeks=200)).status_code == 422


def test_danh_sach_va_bo_loc(client: TestClient):
    client.post("/api/courses", json=_payload(title="IELTS Writing Task 2", skill="writing"))
    client.post("/api/courses", json=_payload(title="IELTS Speaking Pro", skill="speaking"))
    client.post(
        "/api/courses",
        json=_payload(title="IELTS Full Skills", status="published", start_date="2026-10-01"),
    )

    all_items = client.get("/api/courses").json()
    assert all_items["total"] == 3
    assert all_items["items"][0]["title"] == "IELTS Full Skills"   # mới nhất trước

    assert client.get("/api/courses", params={"skill": "writing"}).json()["total"] == 1
    assert client.get("/api/courses", params={"status": "published"}).json()["total"] == 1
    assert client.get("/api/courses", params={"q": "speaking"}).json()["total"] == 1
    assert client.get("/api/courses", params={"q": "khong-co-gi"}).json()["total"] == 0


def test_phan_trang(client: TestClient):
    for i in range(5):
        client.post("/api/courses", json=_payload(title=f"Khóa số {i}"))
    page = client.get("/api/courses", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 5
    assert len(page["items"]) == 2


def test_xem_chi_tiet_va_404(client: TestClient):
    created = client.post("/api/courses", json=_payload()).json()
    assert client.get(f"/api/courses/{created['id']}").json()["slug"] == created["slug"]
    assert client.get("/api/courses/9999").status_code == 404


def test_ten_khong_co_chu_cai_van_ra_slug_hop_le(client: TestClient):
    """Tên toàn ký tự đặc biệt thì slugify trả rỗng — phải rơi về slug dự phòng."""
    body = client.post("/api/courses", json=_payload(title="!!! ??? ***")).json()
    assert body["slug"] == "khoa-hoc"


def test_tim_kiem_khong_coi_phan_tram_la_wildcard(client: TestClient):
    """'%' người dùng gõ phải là ký tự thường, không phải toán tử LIKE."""
    client.post("/api/courses", json=_payload(title="IELTS Speaking Pro"))
    assert client.get("/api/courses", params={"q": "%"}).json()["total"] == 0


def test_health(client: TestClient):
    assert client.get("/api/health").json() == {"status": "ok"}
