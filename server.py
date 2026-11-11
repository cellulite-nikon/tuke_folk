import json
import os
import re
import socket
import sqlite3
import sys
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "nomikai_tuke.db"))
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

DEFAULT_HTML_TEMPLATE = """<div class="report-paper">
  <div class="report-header">
    <div>
      <h1 class="report-title">飲み会ツケ状況報告書</h1>
      <div class="group-badge">グループ: {{group_name}}</div>
    </div>
    <div class="report-meta">
      <div>発行日: {{generated_at}}</div>
      <div class="app-tag">ツケ管理アプリ (Tuke Folk)</div>
    </div>
  </div>

  <div class="total-box">
    <div>
      <div class="total-label">現在の立替額合計（未回収ツケ）</div>
      <div class="total-sub">※グループ全員の合計額</div>
    </div>
    <div class="total-amount">{{total_debt}}</div>
  </div>

  <div class="members-container">
    {{#members}}
    <div class="member-block">
      <div class="member-header">
        <span class="member-name">{{member_name}} 殿</span>
        <span class="member-subtotal">ツケ合計: {{member_total_debt}}</span>
      </div>
      <table class="debt-table">
        <thead>
          <tr>
            <th style="width:25%;">開催日</th>
            <th style="width:40%;">飲み会名</th>
            <th style="width:15%;" class="text-right">会費</th>
            <th style="width:20%;" class="text-right">ツケ額</th>
          </tr>
        </thead>
        <tbody>
          {{#debts}}
          <tr>
            <td>{{event_date}}</td>
            <td><strong>{{event_title}}</strong></td>
            <td class="text-right">{{target_amount}}</td>
            <td class="text-right debt-val">{{debt_amount}}</td>
          </tr>
          {{/debts}}
        </tbody>
      </table>
    </div>
    {{/members}}
  </div>

  <div class="settle-notice">
    <strong>【幹事からのお願い】</strong><br>
    {{notice}}
  </div>
</div>"""

DEFAULT_CSS_TEMPLATE = """/* 報告書ペーパー */
.report-paper {
  max-width: 800px;
  margin: 0 auto;
  background: #ffffff;
  padding: 36px 32px;
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
  border: 1px solid #cbd5e1;
  color: #1e293b;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Hiragino Sans", "Meiryo", sans-serif;
  line-height: 1.5;
}

/* ヘッダー */
.report-header {
  border-bottom: 2px solid #0f172a;
  padding-bottom: 16px;
  margin-bottom: 24px;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
}
.report-title {
  font-size: 1.6rem;
  font-weight: 800;
  color: #0f172a;
  margin: 0;
}
.report-meta {
  text-align: right;
  font-size: 0.85rem;
  color: #64748b;
}
.group-badge {
  display: inline-block;
  background: #e0f2fe;
  color: #0369a1;
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 0.95rem;
  font-weight: 700;
  margin-top: 6px;
}
.app-tag {
  font-size: 0.75rem;
  color: #94a3b8;
  margin-top: 2px;
}

/* 総額ボックス */
.total-box {
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 28px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.total-label {
  font-size: 1rem;
  font-weight: 700;
  color: #991b1b;
}
.total-sub {
  font-size: 0.8rem;
  color: #b91c1c;
  margin-top: 2px;
}
.total-amount {
  font-size: 2rem;
  font-weight: 800;
  color: #dc2626;
}

/* メンバーブロック */
.member-block {
  margin-bottom: 24px;
  page-break-inside: avoid;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  overflow: hidden;
}
.member-header {
  background: #f1f5f9;
  padding: 10px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #cbd5e1;
}
.member-name {
  font-size: 1.15rem;
  font-weight: 800;
  color: #0f172a;
}
.member-subtotal {
  font-size: 1.05rem;
  font-weight: 800;
  color: #dc2626;
}

/* 内訳テーブル */
.debt-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
}
.debt-table th {
  background: #f8fafc;
  color: #64748b;
  font-weight: 600;
  text-align: left;
  padding: 8px 14px;
  border-bottom: 1px solid #cbd5e1;
}
.debt-table td {
  padding: 10px 14px;
  border-bottom: 1px solid #e2e8f0;
}
.debt-table tr:last-child td {
  border-bottom: none;
}
.text-right {
  text-align: right;
}
.debt-val {
  font-weight: 700;
  color: #dc2626;
}

/* 案内メモ */
.settle-notice {
  margin-top: 32px;
  padding: 14px 16px;
  background: #f8fafc;
  border-radius: 8px;
  border-left: 4px solid #0284c7;
  font-size: 0.85rem;
  color: #475569;
}

/* 印刷・PDF用 */
@media print {
  body { background: white !important; padding: 0 !important; }
  .report-paper { border: none !important; box-shadow: none !important; padding: 0 !important; max-width: 100% !important; }
  .member-block { break-inside: avoid; }
}"""

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("SELECT COUNT(*) AS cnt FROM groups")
    if cursor.fetchone()["cnt"] == 0:
        cursor.execute("INSERT INTO groups (name) VALUES (?)", ("メイングループ",))

    cursor.execute("SELECT id FROM groups ORDER BY id ASC LIMIT 1")
    default_group_id = cursor.fetchone()["id"]

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL DEFAULT 1,
        name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("PRAGMA table_info(members)")
    cols = [col["name"] for col in cursor.fetchall()]
    if "group_id" not in cols:
        cursor.execute(f"ALTER TABLE members ADD COLUMN group_id INTEGER NOT NULL DEFAULT {default_group_id}")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL DEFAULT 1,
        title TEXT NOT NULL,
        event_date TEXT NOT NULL,
        default_fee INTEGER NOT NULL DEFAULT 5000,
        actual_cost INTEGER DEFAULT NULL, -- 実際にお店に支払った実費（手入力）
        is_archived INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(group_id) REFERENCES groups(id) ON DELETE CASCADE
    );
    """)
    cursor.execute("PRAGMA table_info(events)")
    cols = [col["name"] for col in cursor.fetchall()]
    if "group_id" not in cols:
        cursor.execute(f"ALTER TABLE events ADD COLUMN group_id INTEGER NOT NULL DEFAULT {default_group_id}")
    if "actual_cost" not in cols:
        cursor.execute("ALTER TABLE events ADD COLUMN actual_cost INTEGER DEFAULT NULL")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        member_id INTEGER NOT NULL,
        target_amount INTEGER NOT NULL,
        paid_amount INTEGER NOT NULL DEFAULT 0,
        debt_amount INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'UNPAID',
        memo TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
        FOREIGN KEY(member_id) REFERENCES members(id) ON DELETE CASCADE,
        UNIQUE(event_id, member_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settlements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        memo TEXT,
        settled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(member_id) REFERENCES members(id) ON DELETE CASCADE
    );
    """)

    # PDF/帳票デザインテンプレートテーブル
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS report_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        html_content TEXT NOT NULL,
        css_content TEXT NOT NULL,
        notice_text TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("SELECT COUNT(*) AS cnt FROM report_templates WHERE name = 'default'")
    if cursor.fetchone()["cnt"] == 0:
        cursor.execute("""
            INSERT INTO report_templates (name, html_content, css_content, notice_text)
            VALUES ('default', ?, ?, '上記をご確認いただき、PayPayまたは次回集合時にお支払い・精算をお願いいたします。<br>精算完了次第、アプリ上で消込を行います。')
        """, (DEFAULT_HTML_TEMPLATE, DEFAULT_CSS_TEMPLATE))

    conn.commit()
    conn.close()

class RequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message, status=400):
        self._send_json({"error": message}, status=status)

    def _read_json(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length).decode("utf-8")
        try:
            return json.loads(body)
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path.startswith("/api/"):
            self.handle_api_get(path, query)
        else:
            self.handle_static(path)

    def handle_static(self, path):
        if path == "/" or path == "":
            path = "/index.html"
        file_path = os.path.join(STATIC_DIR, path.lstrip("/"))
        if not os.path.exists(file_path) or os.path.isdir(file_path):
            file_path = os.path.join(STATIC_DIR, "index.html")

        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".svg": "image/svg+xml"
        }
        ext = os.path.splitext(file_path)[1]
        content_type = content_types.get(ext, "application/octet-stream")

        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_response(404)
            self.end_headers()

    def handle_api_get(self, path, query):
        conn = get_db()
        cursor = conn.cursor()

        # データベース書き出し（エクスポート・バックアップ）
        if path == "/api/backup/export":
            conn.close()
            if not os.path.exists(DB_PATH):
                self._send_error_json("データベースファイルが存在しません", 404)
                return

            import tempfile
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"nomikai_tuke_{timestamp}.db"

            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                tmp_path = tmp.name

            try:
                src_conn = sqlite3.connect(DB_PATH)
                dst_conn = sqlite3.connect(tmp_path)
                src_conn.backup(dst_conn)
                dst_conn.close()
                src_conn.close()

                with open(tmp_path, "rb") as f:
                    content = f.read()

                os.remove(tmp_path)

                self.send_response(200)
                self.send_header("Content-Type", "application/x-sqlite3")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                if os.path.exists(tmp_path):
                    try: os.remove(tmp_path)
                    except Exception: pass
                self._send_error_json(f"エクスポート中にエラーが発生しました: {str(e)}", 500)
            return

        # テンプレート取得API
        if path == "/api/template":
            cursor.execute("SELECT * FROM report_templates WHERE name = 'default'")
            row = cursor.fetchone()
            if row:
                res = dict(row)
            else:
                res = {
                    "html_content": DEFAULT_HTML_TEMPLATE,
                    "css_content": DEFAULT_CSS_TEMPLATE,
                    "notice_text": "上記をご確認いただき、PayPayまたは次回集合時にお支払い・精算をお願いいたします。"
                }
            conn.close()
            self._send_json(res)
            return

        # グループIDの取得
        group_id_param = query.get("group_id", [None])[0]
        if group_id_param and group_id_param.isdigit():
            group_id = int(group_id_param)
        else:
            cursor.execute("SELECT id FROM groups ORDER BY id ASC LIMIT 1")
            first_g = cursor.fetchone()
            group_id = first_g["id"] if first_g else 1

        # グループ一覧
        if path == "/api/groups":
            cursor.execute("""
                SELECT g.*,
                       (SELECT COUNT(*) FROM members m WHERE m.group_id = g.id) AS member_count,
                       (SELECT COUNT(*) FROM events e WHERE e.group_id = g.id) AS event_count,
                       (SELECT COALESCE(SUM(p.debt_amount), 0)
                        FROM payments p
                        JOIN events e ON p.event_id = e.id
                        WHERE e.group_id = g.id AND p.status IN ('UNPAID', 'PARTIAL')) AS total_debt
                FROM groups g
                ORDER BY g.id ASC
            """)
            groups = [dict(row) for row in cursor.fetchall()]
            conn.close()
            self._send_json(groups)
            return

        # グループ全体のツケ内訳レポート
        match_report = re.match(r"^/api/groups/(\d+)/report$", path)
        if match_report:
            g_id = int(match_report.group(1))
            cursor.execute("SELECT * FROM groups WHERE id = ?", (g_id,))
            group_row = cursor.fetchone()
            if not group_row:
                conn.close()
                self._send_error_json("グループが見つかりません", 404)
                return

            cursor.execute("""
                SELECT COALESCE(SUM(p.debt_amount), 0) AS total_debt
                FROM payments p
                JOIN events e ON p.event_id = e.id
                WHERE e.group_id = ? AND p.status IN ('UNPAID', 'PARTIAL')
            """, (g_id,))
            total_debt = cursor.fetchone()["total_debt"]

            cursor.execute("""
                SELECT m.id, m.name, COALESCE(SUM(p.debt_amount), 0) AS member_total_debt
                FROM members m
                JOIN payments p ON m.id = p.member_id
                JOIN events e ON p.event_id = e.id
                WHERE m.group_id = ? AND p.status IN ('UNPAID', 'PARTIAL')
                GROUP BY m.id, m.name
                HAVING member_total_debt > 0
                ORDER BY member_total_debt DESC, m.name ASC
            """, (g_id,))
            member_rows = cursor.fetchall()

            members_data = []
            for m_row in member_rows:
                mid = m_row["id"]
                cursor.execute("""
                    SELECT p.id, p.target_amount, p.paid_amount, p.debt_amount, p.status,
                           e.title AS event_title, e.event_date
                    FROM payments p
                    JOIN events e ON p.event_id = e.id
                    WHERE p.member_id = ? AND e.group_id = ? AND p.status IN ('UNPAID', 'PARTIAL')
                    ORDER BY e.event_date ASC, e.id ASC
                """, (mid, g_id))
                debts = [dict(r) for r in cursor.fetchall()]
                members_data.append({
                    "id": mid,
                    "name": m_row["name"],
                    "total_debt": m_row["member_total_debt"],
                    "debts": debts
                })

            # テンプレート取得
            cursor.execute("SELECT * FROM report_templates WHERE name = 'default'")
            tmpl = cursor.fetchone()
            template_info = dict(tmpl) if tmpl else {
                "html_content": DEFAULT_HTML_TEMPLATE,
                "css_content": DEFAULT_CSS_TEMPLATE,
                "notice_text": "上記をご確認いただき、PayPayまたは次回集合時にお支払い・精算をお願いいたします。"
            }

            conn.close()
            self._send_json({
                "group": dict(group_row),
                "generated_at": datetime.now().strftime("%Y年%m月%d日 %H:%M"),
                "total_debt": total_debt,
                "members": members_data,
                "template": template_info
            })
            return

        # サマリー情報（立替額、メンバー別ツケ、および実費との差額）
        if path == "/api/summary":
            # 現在の建て替え残高（未回収ツケ合計）
            cursor.execute("""
                SELECT COALESCE(SUM(p.debt_amount), 0) AS total_debt 
                FROM payments p
                JOIN events e ON p.event_id = e.id
                WHERE e.group_id = ? AND p.status IN ('UNPAID', 'PARTIAL')
            """, (group_id,))
            total_debt = cursor.fetchone()["total_debt"]

            # メンバーごとの未回収ツケ合計
            cursor.execute("""
                SELECT m.id, m.name, 
                       COALESCE(SUM(p.debt_amount), 0) AS debt_total,
                       COUNT(p.id) AS event_count
                FROM members m
                JOIN payments p ON m.id = p.member_id
                JOIN events e ON p.event_id = e.id
                WHERE m.group_id = ? AND p.status IN ('UNPAID', 'PARTIAL')
                GROUP BY m.id, m.name
                HAVING debt_total > 0
                ORDER BY debt_total DESC
            """, (group_id,))
            debts_by_member = [dict(row) for row in cursor.fetchall()]

            # 幹事余剰金（実費と回収済み金額の差額）の計算
            # 参加者数のJOINによる重複加算（直積）を防ぐためサブクエリで正確に集計
            cursor.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM events WHERE group_id = ? AND actual_cost IS NOT NULL) AS event_count_with_cost,
                    (SELECT COALESCE(SUM(actual_cost), 0) FROM events WHERE group_id = ? AND actual_cost IS NOT NULL) AS total_actual_cost,
                    (SELECT COALESCE(SUM(p.target_amount), 0) 
                     FROM payments p 
                     JOIN events e ON p.event_id = e.id 
                     WHERE e.group_id = ? AND e.actual_cost IS NOT NULL) AS total_target_amount,
                    (SELECT COALESCE(SUM(p.paid_amount), 0) 
                     FROM payments p 
                     JOIN events e ON p.event_id = e.id 
                     WHERE e.group_id = ? AND e.actual_cost IS NOT NULL) AS total_paid_amount
            """, (group_id, group_id, group_id, group_id))
            cost_summary = cursor.fetchone()

            actual_cost_total = cost_summary["total_actual_cost"]
            target_amount_for_cost = cost_summary["total_target_amount"]
            paid_amount_for_cost = cost_summary["total_paid_amount"]
            events_with_cost = cost_summary["event_count_with_cost"]

            # 差額（余剰金） = (回収済み金額) - (店舗支払額)
            surplus = paid_amount_for_cost - actual_cost_total

            cursor.execute("SELECT * FROM groups WHERE id = ?", (group_id,))
            group_info = dict(cursor.fetchone() or {"id": group_id, "name": "不明"})

            conn.close()
            self._send_json({
                "group": group_info,
                "total_debt": total_debt,
                "debts_by_member": debts_by_member,
                "profit_summary": {
                    "has_actual_cost": events_with_cost > 0,
                    "total_actual_cost": actual_cost_total,
                    "total_target_amount": target_amount_for_cost,
                    "total_paid_amount": paid_amount_for_cost,
                    "surplus": surplus # (回収済み金額) - (店舗支払額)
                }
            })
            return

        # メンバー一覧
        if path == "/api/members":
            cursor.execute("""
                SELECT m.*, 
                       COALESCE(SUM(CASE WHEN p.status IN ('UNPAID', 'PARTIAL') THEN p.debt_amount ELSE 0 END), 0) AS current_debt
                FROM members m
                LEFT JOIN payments p ON m.id = p.member_id
                WHERE m.group_id = ?
                GROUP BY m.id
                ORDER BY m.name ASC
            """, (group_id,))
            members = [dict(row) for row in cursor.fetchall()]
            conn.close()
            self._send_json(members)
            return

        # イベント一覧
        if path == "/api/events":
            cursor.execute("""
                SELECT e.*, 
                       COUNT(p.id) AS participant_count,
                       COALESCE(SUM(p.target_amount), 0) AS total_target,
                       COALESCE(SUM(p.paid_amount), 0) AS total_paid,
                       COALESCE(SUM(p.debt_amount), 0) AS total_debt
                FROM events e
                LEFT JOIN payments p ON e.id = p.event_id
                WHERE e.group_id = ?
                GROUP BY e.id
                ORDER BY e.event_date DESC, e.id DESC
            """, (group_id,))
            events = []
            for row in cursor.fetchall():
                ed = dict(row)
                if ed.get("actual_cost") is not None:
                    # 余剰金 = (回収済み金額) - (店舗支払額)
                    ed["surplus"] = ed["total_paid"] - ed["actual_cost"]
                else:
                    ed["surplus"] = None
                events.append(ed)
            conn.close()
            self._send_json(events)
            return

        # イベント詳細
        match_event = re.match(r"^/api/events/(\d+)$", path)
        if match_event:
            event_id = int(match_event.group(1))
            cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
            event = cursor.fetchone()
            if not event:
                conn.close()
                self._send_error_json("イベントが見つかりません", 404)
                return

            cursor.execute("""
                SELECT p.*, m.name AS member_name
                FROM payments p
                JOIN members m ON p.member_id = m.id
                WHERE p.event_id = ?
                ORDER BY m.name ASC
            """, (event_id,))
            participants = [dict(row) for row in cursor.fetchall()]

            total_target = sum(p["target_amount"] for p in participants)
            total_paid = sum(p["paid_amount"] for p in participants)
            total_debt = sum(p["debt_amount"] for p in participants)

            event_dict = dict(event)
            actual_cost = event_dict.get("actual_cost")
            # 余剰金 = (回収済み金額) - (店舗支払額)
            surplus = (total_paid - actual_cost) if actual_cost is not None else None

            conn.close()
            self._send_json({
                "event": event_dict,
                "participants": participants,
                "stats": {
                    "total_target": total_target,
                    "total_paid": total_paid,
                    "total_debt": total_debt,
                    "actual_cost": actual_cost,
                    "surplus": surplus,
                    "count": len(participants)
                }
            })
            return

        # メンバーのツケ明細（未回収ツケ ＋ 過去の返済履歴）
        match_member_debts = re.match(r"^/api/members/(\d+)/debts$", path)
        if match_member_debts:
            member_id = int(match_member_debts.group(1))
            cursor.execute("SELECT * FROM members WHERE id = ?", (member_id,))
            member = cursor.fetchone()
            if not member:
                conn.close()
                self._send_error_json("メンバーが見つかりません", 404)
                return

            cursor.execute("""
                SELECT p.*, e.title AS event_title, e.event_date
                FROM payments p
                JOIN events e ON p.event_id = e.id
                WHERE p.member_id = ? AND p.status IN ('UNPAID', 'PARTIAL')
                ORDER BY e.event_date ASC
            """, (member_id,))
            debts = [dict(row) for row in cursor.fetchall()]
            total_debt = sum(d["debt_amount"] for d in debts)

            # 過去の返済履歴（直近10件）
            cursor.execute("""
                SELECT id, amount, memo, settled_at
                FROM settlements
                WHERE member_id = ?
                ORDER BY settled_at DESC, id DESC
                LIMIT 10
            """, (member_id,))
            settlements = [dict(row) for row in cursor.fetchall()]

            conn.close()
            self._send_json({
                "member": dict(member),
                "debts": debts,
                "settlements": settlements,
                "total_debt": total_debt
            })
            return

        conn.close()
        self._send_error_json("Not Found", 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # データベースインポート（復元）
        if path == "/api/backup/import":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self._send_error_json("ファイルデータが空です")
                return

            db_bytes = self.rfile.read(content_length)

            # SQLite3ヘッダー検証 (先頭16バイト: 'SQLite format 3\0')
            if len(db_bytes) < 16 or not db_bytes.startswith(b"SQLite format 3\x00"):
                self._send_error_json("無効なSQLiteデータベースファイルです（.dbファイルを選択してください）")
                return

            import tempfile, shutil
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
                tmp.write(db_bytes)
                tmp_path = tmp.name

            try:
                test_conn = sqlite3.connect(tmp_path)
                test_cur = test_conn.cursor()
                test_cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                test_conn.close()
            except Exception as e:
                if os.path.exists(tmp_path):
                    try: os.remove(tmp_path)
                    except Exception: pass
                self._send_error_json(f"データベースファイルが破損しています: {str(e)}")
                return

            # 現行DBの自動バックアップを作成
            if os.path.exists(DB_PATH):
                backup_name = DB_PATH + f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                try:
                    shutil.copy2(DB_PATH, backup_name)
                except Exception:
                    pass

            try:
                shutil.move(tmp_path, DB_PATH)
                init_db()
                self._send_json({"success": True, "message": "データベースを正常にインポートしました"})
            except Exception as e:
                self._send_error_json(f"ファイルの置き換え中にエラーが発生しました: {str(e)}", 500)
            return

        body = self._read_json()
        conn = get_db()
        cursor = conn.cursor()

        # テンプレート保存API
        if path == "/api/template":
            html_content = body.get("html_content", DEFAULT_HTML_TEMPLATE)
            css_content = body.get("css_content", DEFAULT_CSS_TEMPLATE)
            notice_text = body.get("notice_text", "")
            cursor.execute("""
                INSERT INTO report_templates (name, html_content, css_content, notice_text, updated_at)
                VALUES ('default', ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    html_content = excluded.html_content,
                    css_content = excluded.css_content,
                    notice_text = excluded.notice_text,
                    updated_at = CURRENT_TIMESTAMP
            """, (html_content, css_content, notice_text))
            conn.commit()
            conn.close()
            self._send_json({"success": True})
            return

        # テンプレート初期化（リセット）API
        if path == "/api/template/reset":
            cursor.execute("""
                UPDATE report_templates 
                SET html_content = ?, css_content = ?, 
                    notice_text = '上記をご確認いただき、PayPayまたは次回集合時にお支払い・精算をお願いいたします。<br>精算完了次第、アプリ上で消込を行います。',
                    updated_at = CURRENT_TIMESTAMP
                WHERE name = 'default'
            """, (DEFAULT_HTML_TEMPLATE, DEFAULT_CSS_TEMPLATE))
            conn.commit()
            conn.close()
            self._send_json({
                "success": True,
                "html_content": DEFAULT_HTML_TEMPLATE,
                "css_content": DEFAULT_CSS_TEMPLATE,
                "notice_text": "上記をご確認いただき、PayPayまたは次回集合時にお支払い・精算をお願いいたします。<br>精算完了次第、アプリ上で消込を行います。"
            })
            return

        # 新規グループ作成
        if path == "/api/groups":
            name = body.get("name", "").strip()
            if not name:
                conn.close()
                self._send_error_json("グループ名を入力してください")
                return
            cursor.execute("INSERT INTO groups (name) VALUES (?)", (name,))
            conn.commit()
            new_id = cursor.lastrowid
            conn.close()
            self._send_json({"id": new_id, "name": name}, 201)
            return

        # メンバー追加
        if path == "/api/members":
            name = body.get("name", "").strip()
            group_id = int(body.get("group_id", 1))
            if not name:
                conn.close()
                self._send_error_json("名前を入力してください")
                return
            cursor.execute("SELECT id FROM members WHERE name = ? AND group_id = ?", (name, group_id))
            if cursor.fetchone():
                conn.close()
                self._send_error_json("このグループに同名のメンバーが既に存在します")
                return

            cursor.execute("INSERT INTO members (name, group_id) VALUES (?, ?)", (name, group_id))
            conn.commit()
            new_id = cursor.lastrowid
            conn.close()
            self._send_json({"id": new_id, "name": name, "group_id": group_id}, 201)
            return

        # イベント作成
        if path == "/api/events":
            title = body.get("title", "").strip()
            group_id = int(body.get("group_id", 1))
            event_date = body.get("event_date", "").strip() or datetime.now().strftime("%Y-%m-%d")
            default_fee = int(body.get("default_fee", 5000))
            raw_cost = body.get("actual_cost")
            actual_cost = int(raw_cost) if raw_cost is not None and str(raw_cost).strip() != "" else None
            member_ids = body.get("member_ids", [])

            if not title:
                conn.close()
                self._send_error_json("飲み会名を入力してください")
                return

            cursor.execute("INSERT INTO events (title, event_date, default_fee, actual_cost, group_id) VALUES (?, ?, ?, ?, ?)",
                           (title, event_date, default_fee, actual_cost, group_id))
            event_id = cursor.lastrowid

            for mid in member_ids:
                cursor.execute("""
                    INSERT OR IGNORE INTO payments (event_id, member_id, target_amount, paid_amount, debt_amount, status)
                    VALUES (?, ?, ?, 0, ?, 'UNPAID')
                """, (event_id, mid, default_fee, default_fee))

            conn.commit()
            conn.close()
            self._send_json({"id": event_id, "title": title, "event_date": event_date, "group_id": group_id}, 201)
            return

        # イベントへの参加者追加
        match_add_part = re.match(r"^/api/events/(\d+)/participants$", path)
        if match_add_part:
            event_id = int(match_add_part.group(1))
            member_id = body.get("member_id")
            new_name = body.get("new_member_name", "").strip()

            cursor.execute("SELECT default_fee, group_id FROM events WHERE id = ?", (event_id,))
            event = cursor.fetchone()
            if not event:
                conn.close()
                self._send_error_json("イベントが見つかりません", 404)
                return

            target_amount = int(body.get("target_amount", event["default_fee"]))
            event_group_id = event["group_id"]

            if not member_id and new_name:
                cursor.execute("SELECT id FROM members WHERE name = ? AND group_id = ?", (new_name, event_group_id))
                existing = cursor.fetchone()
                if existing:
                    member_id = existing["id"]
                else:
                    cursor.execute("INSERT INTO members (name, group_id) VALUES (?, ?)", (new_name, event_group_id))
                    member_id = cursor.lastrowid

            if not member_id:
                conn.close()
                self._send_error_json("参加者を指定してください")
                return

            try:
                cursor.execute("""
                    INSERT INTO payments (event_id, member_id, target_amount, paid_amount, debt_amount, status)
                    VALUES (?, ?, ?, 0, ?, 'UNPAID')
                """, (event_id, member_id, target_amount, target_amount))
                conn.commit()
                conn.close()
                self._send_json({"success": True}, 201)
            except sqlite3.IntegrityError:
                conn.close()
                self._send_error_json("この参加者は既に追加されています")
            return

        # 清算
        if path == "/api/settlements":
            member_id = body.get("member_id")
            amount = int(body.get("amount", 0))
            memo = body.get("memo", "").strip()
            settled_at_raw = body.get("settled_at", "").strip()
            if settled_at_raw:
                # '2026-11-11T19:30' または '2026-11-11 19:30:00' などのフォーマットを正規化
                settled_at = settled_at_raw.replace("T", " ")
                if len(settled_at) == 16:  # YYYY-MM-DD HH:MM
                    settled_at += ":00"
            else:
                settled_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if not member_id or amount <= 0:
                conn.close()
                self._send_error_json("有効な返済額を入力してください")
                return

            cursor.execute("""
                SELECT id, target_amount, paid_amount, debt_amount
                FROM payments
                WHERE member_id = ? AND status IN ('UNPAID', 'PARTIAL')
                ORDER BY id ASC
            """, (member_id,))
            rows = cursor.fetchall()

            remaining = amount
            for row in rows:
                if remaining <= 0:
                    break
                p_id = row["id"]
                p_debt = row["debt_amount"]
                p_paid = row["paid_amount"]

                if remaining >= p_debt:
                    new_paid = p_paid + p_debt
                    cursor.execute("""
                        UPDATE payments 
                        SET paid_amount = ?, debt_amount = 0, status = 'SETTLED'
                        WHERE id = ?
                    """, (new_paid, p_id))
                    remaining -= p_debt
                else:
                    new_paid = p_paid + remaining
                    new_debt = p_debt - remaining
                    cursor.execute("""
                        UPDATE payments 
                        SET paid_amount = ?, debt_amount = ?, status = 'PARTIAL'
                        WHERE id = ?
                    """, (new_paid, new_debt, p_id))
                    remaining = 0

            cursor.execute("INSERT INTO settlements (member_id, amount, memo, settled_at) VALUES (?, ?, ?, ?)",
                           (member_id, amount, memo, settled_at))
            conn.commit()
            conn.close()
            self._send_json({"success": True, "settled_amount": amount, "settled_at": settled_at})
            return

        conn.close()
        self._send_error_json("Not Found", 404)

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_json()
        conn = get_db()
        cursor = conn.cursor()

        # 飲み会（イベント）情報編集
        match_event_edit = re.match(r"^/api/events/(\d+)$", path)
        if match_event_edit:
            event_id = int(match_event_edit.group(1))
            cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
            event = cursor.fetchone()
            if not event:
                conn.close()
                self._send_error_json("イベントが見つかりません", 404)
                return

            title = body.get("title", event["title"]).strip()
            event_date = body.get("event_date", event["event_date"]).strip()
            default_fee = int(body.get("default_fee", event["default_fee"]))

            raw_cost = body.get("actual_cost")
            if raw_cost is not None and str(raw_cost).strip() != "":
                actual_cost = int(raw_cost)
            elif "actual_cost" in body and (raw_cost is None or str(raw_cost).strip() == ""):
                actual_cost = None
            else:
                actual_cost = event["actual_cost"]

            if not title:
                conn.close()
                self._send_error_json("飲み会名を入力してください")
                return

            cursor.execute("""
                UPDATE events 
                SET title = ?, event_date = ?, default_fee = ?, actual_cost = ?
                WHERE id = ?
            """, (title, event_date, default_fee, actual_cost, event_id))
            conn.commit()
            conn.close()
            self._send_json({"id": event_id, "title": title, "event_date": event_date, "default_fee": default_fee, "actual_cost": actual_cost})
            return

        # グループ名編集
        match_group = re.match(r"^/api/groups/(\d+)$", path)
        if match_group:
            group_id = int(match_group.group(1))
            name = body.get("name", "").strip()
            if not name:
                conn.close()
                self._send_error_json("グループ名を入力してください")
                return
            cursor.execute("UPDATE groups SET name = ? WHERE id = ?", (name, group_id))
            conn.commit()
            conn.close()
            self._send_json({"id": group_id, "name": name})
            return

        # メンバー名編集
        match_member = re.match(r"^/api/members/(\d+)$", path)
        if match_member:
            member_id = int(match_member.group(1))
            name = body.get("name", "").strip()
            if not name:
                conn.close()
                self._send_error_json("メンバー名を入力してください")
                return

            cursor.execute("SELECT group_id FROM members WHERE id = ?", (member_id,))
            m = cursor.fetchone()
            if not m:
                conn.close()
                self._send_error_json("メンバーが見つかりません", 404)
                return

            cursor.execute("SELECT id FROM members WHERE name = ? AND group_id = ? AND id != ?", (name, m["group_id"], member_id))
            if cursor.fetchone():
                conn.close()
                self._send_error_json("このグループに同名のメンバーが既に存在します")
                return

            cursor.execute("UPDATE members SET name = ? WHERE id = ?", (name, member_id))
            conn.commit()
            conn.close()
            self._send_json({"id": member_id, "name": name})
            return

        # 支払ステータス更新
        match_pay = re.match(r"^/api/payments/(\d+)$", path)
        if match_pay:
            payment_id = int(match_pay.group(1))
            cursor.execute("SELECT * FROM payments WHERE id = ?", (payment_id,))
            payment = cursor.fetchone()
            if not payment:
                conn.close()
                self._send_error_json("支払いデータが見つかりません", 404)
                return

            action = body.get("action")
            target_amount = int(body.get("target_amount", payment["target_amount"]))

            # 参加メンバーの差し替え
            new_member_id = body.get("member_id")
            if new_member_id and int(new_member_id) != payment["member_id"]:
                new_mid = int(new_member_id)
                cursor.execute("SELECT id FROM payments WHERE event_id = ? AND member_id = ? AND id != ?",
                               (payment["event_id"], new_mid, payment_id))
                if cursor.fetchone():
                    conn.close()
                    self._send_error_json("このメンバーは既にこの飲み会に参加しています")
                    return
                cursor.execute("UPDATE payments SET member_id = ? WHERE id = ?", (new_mid, payment_id))

            if action == "paid":
                cursor.execute("""
                    UPDATE payments 
                    SET target_amount = ?, paid_amount = ?, debt_amount = 0, status = 'PAID'
                    WHERE id = ?
                """, (target_amount, target_amount, payment_id))
            elif action == "unpaid":
                cursor.execute("""
                    UPDATE payments 
                    SET target_amount = ?, paid_amount = 0, debt_amount = ?, status = 'UNPAID'
                    WHERE id = ?
                """, (target_amount, target_amount, payment_id))
            elif action == "partial":
                paid_amount = int(body.get("paid_amount", 0))
                debt_amount = max(0, target_amount - paid_amount)
                status = "PAID" if debt_amount == 0 else ("PARTIAL" if paid_amount > 0 else "UNPAID")
                cursor.execute("""
                    UPDATE payments 
                    SET target_amount = ?, paid_amount = ?, debt_amount = ?, status = ?
                    WHERE id = ?
                """, (target_amount, paid_amount, debt_amount, status, payment_id))
            elif action == "update_fee":
                curr_paid = payment["paid_amount"]
                if payment["status"] == "PAID":
                    cursor.execute("""
                        UPDATE payments 
                        SET target_amount = ?, paid_amount = ?, debt_amount = 0
                        WHERE id = ?
                    """, (target_amount, target_amount, payment_id))
                else:
                    debt_amount = max(0, target_amount - curr_paid)
                    cursor.execute("""
                        UPDATE payments 
                        SET target_amount = ?, debt_amount = ?
                        WHERE id = ?
                    """, (target_amount, debt_amount, payment_id))
            else:
                conn.close()
                self._send_error_json("無効なアクションです")
                return

            conn.commit()
            cursor.execute("""
                SELECT p.*, m.name AS member_name
                FROM payments p
                JOIN members m ON p.member_id = m.id
                WHERE p.id = ?
            """, (payment_id,))
            updated = dict(cursor.fetchone())
            conn.close()
            self._send_json(updated)
            return

        conn.close()
        self._send_error_json("Not Found", 404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        conn = get_db()
        cursor = conn.cursor()

        # グループ削除
        match_del_group = re.match(r"^/api/groups/(\d+)$", path)
        if match_del_group:
            group_id = int(match_del_group.group(1))
            cursor.execute("SELECT COUNT(*) AS cnt FROM groups")
            if cursor.fetchone()["cnt"] <= 1:
                conn.close()
                self._send_error_json("最後の1つのグループは削除できません")
                return

            cursor.execute("""
                DELETE FROM payments WHERE event_id IN (SELECT id FROM events WHERE group_id = ?)
            """, (group_id,))
            cursor.execute("DELETE FROM events WHERE group_id = ?", (group_id,))
            cursor.execute("DELETE FROM members WHERE group_id = ?", (group_id,))
            cursor.execute("DELETE FROM groups WHERE id = ?", (group_id,))
            conn.commit()
            conn.close()
            self._send_json({"success": True})
            return

        # メンバー削除
        match_del_member = re.match(r"^/api/members/(\d+)$", path)
        if match_del_member:
            member_id = int(match_del_member.group(1))
            cursor.execute("DELETE FROM payments WHERE member_id = ?", (member_id,))
            cursor.execute("DELETE FROM settlements WHERE member_id = ?", (member_id,))
            cursor.execute("DELETE FROM members WHERE id = ?", (member_id,))
            conn.commit()
            conn.close()
            self._send_json({"success": True})
            return

        # 参加者の削除
        match_del_part = re.match(r"^/api/payments/(\d+)$", path)
        if match_del_part:
            payment_id = int(match_del_part.group(1))
            cursor.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
            conn.commit()
            conn.close()
            self._send_json({"success": True})
            return

        # イベントの削除
        match_del_event = re.match(r"^/api/events/(\d+)$", path)
        if match_del_event:
            event_id = int(match_del_event.group(1))
            cursor.execute("DELETE FROM payments WHERE event_id = ?", (event_id,))
            cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
            conn.commit()
            conn.close()
            self._send_json({"success": True})
            return

        conn.close()
        self._send_error_json("Not Found", 404)

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def run_server(port=8765):
    init_db()
    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(server_address, RequestHandler)
    local_ip = get_local_ip()
    print("=" * 56)
    print(" 🍻 飲み会ツケ管理アプリ (Tuke Folk) が起動しました！")
    print("=" * 56)
    print(f" 💻 PCから開く:      http://localhost:{port}")
    if local_ip != "127.0.0.1":
        print(f" 📱 スマホから開く:    http://{local_ip}:{port}")
        print("    (※PCと同じWi-Fiに接続したスマホのブラウザで開いてください)")
    print("=" * 56)
    print(" 停止するには Ctrl + C を押してください")
    print("=" * 56)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nサーバーを停止しました")

if __name__ == "__main__":
    port = 8765
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    run_server(port)
