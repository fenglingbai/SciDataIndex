#!/usr/bin/env python3
"""API Key 申请管理脚本（管理员在服务器上执行）。

用法（在 scidataindex/web 目录下，或用 python -m 方式）：
    python manage_keys.py list                 # 列出待审核(pending)申请
    python manage_keys.py list-all             # 列出全部记录
    python manage_keys.py show [email]         # 查看完整 邮箱-查询码-key（不带参数列出全部 active）
    python manage_keys.py approve <email>      # 激活并自动发送"已通过"邮件（含查询码）
    python manage_keys.py revoke <email>       # 吊销

用户反馈管理：
    python manage_keys.py feedback-list [status] [type]   # 列出反馈（可按状态/类型筛选，均选填）
    python manage_keys.py feedback-show <id>              # 查看单条反馈详情
    python manage_keys.py feedback-set <id> <status>      # 更新反馈处理状态

反馈状态（按类型区分）：
    problem（问题反馈）：new 待处理 → processing 处理中 → done 已处理
    dataset（数据集建议）：new 待处理 → integrated 已整合进数据池 / rejected 不采纳
"""

from __future__ import annotations

import sys
from pathlib import Path

# 保证可以 import api 包（脚本位于 web/ 下）
sys.path.insert(0, str(Path(__file__).resolve().parent))

from api import keys_db, mailer  # noqa: E402
from api import feedback as feedback_db  # noqa: E402


def _fmt(rec: dict) -> str:
    return (f"  {rec['email']:<32} status={rec['status']:<8} "
            f"code={rec['query_code']} created={rec['created_at']} "
            f"purpose={rec['purpose'][:40]}")


def cmd_list(status: str | None) -> None:
    recs = keys_db.list_by_status(status)
    if not recs:
        print("（无记录）")
        return
    for r in recs:
        print(_fmt(r))
    print(f"\n共 {len(recs)} 条")


def cmd_show(email: str | None) -> None:
    """查看完整 邮箱-查询码-key 三元组。不带参数时列出全部 active。"""
    if email:
        rec = keys_db.get_by_email(email.strip().lower())
        if not rec:
            print(f"未找到申请记录: {email}")
            sys.exit(1)
        recs = [rec]
    else:
        recs = keys_db.list_by_status("active")
        if not recs:
            print("（无 active 记录）")
            return
    for r in recs:
        print(f"  email      = {r['email']}")
        print(f"  query_code = {r['query_code']}")
        print(f"  key        = {r['key']}")
        print(f"  status     = {r['status']}  created={r['created_at']}  approved={r['approved_at'] or '-'}")
        print()


def cmd_approve(email: str) -> None:
    email = email.strip().lower()
    rec = keys_db.get_by_email(email)
    if not rec:
        print(f"未找到申请记录: {email}")
        sys.exit(1)
    if rec["status"] == "active":
        print(f"该邮箱已是 active，key={rec['key']}")
        return
    keys_db.approve(email)
    print(f"已激活: {email}")
    print(f"  key        = {rec['key']}")
    print(f"  query_code = {rec['query_code']}")
    try:
        mailer.send_approved_mail(email, rec["query_code"])
        keys_db.touch_mail(email)
        print(f"  已通过邮件发送查询码 -> {email}")
    except Exception as e:
        print(f"  [警告] 邮件发送失败: {e}")
        print("  可稍后执行 approve 重发，或手动告知用户查询码")


def cmd_revoke(email: str) -> None:
    email = email.strip().lower()
    rec = keys_db.get_by_email(email)
    if not rec:
        print(f"未找到申请记录: {email}")
        sys.exit(1)
    keys_db.revoke(email)
    print(f"已吊销: {email}（key={rec['key']} 立即失效）")


# ---- 用户反馈管理 ----

def _fmt_feedback(rec: dict) -> str:
    if rec["type"] == "problem":
        summary = rec["content"].replace("\n", " ")[:50]
    else:
        summary = f"{rec['dataset_name']} | {rec['dataset_url']}"[:50]
    email = rec["email"] or "-"
    return (f"  [{rec['id']}] {rec['type']:<8} status={rec['status']:<11} "
            f"{rec['created_at']}  email={email:<28} {summary}")


def cmd_feedback_list(status: str | None, ftype: str | None) -> None:
    recs = feedback_db.list_feedback(status=status, ftype=ftype)
    if not recs:
        print("（无记录）")
        return
    for r in recs:
        print(_fmt_feedback(r))
    print(f"\n共 {len(recs)} 条")


def cmd_feedback_show(fid: int) -> None:
    rec = feedback_db.get_feedback(fid)
    if not rec:
        print(f"未找到反馈记录: id={fid}")
        sys.exit(1)
    print(f"  id         = {rec['id']}")
    print(f"  type       = {rec['type']}")
    print(f"  status     = {rec['status']}")
    if rec["type"] == "problem":
        print(f"  content    = {rec['content']}")
    else:
        print(f"  dataset    = {rec['dataset_name']}")
        print(f"  url        = {rec['dataset_url']}")
    print(f"  email      = {rec['email'] or '-'}")
    print(f"  client_ip  = {rec['client_ip']}")
    print(f"  created_at = {rec['created_at']}  updated_at = {rec['updated_at'] or '-'}")


def cmd_feedback_set(fid: int, status: str) -> None:
    err = feedback_db.set_status(fid, status.strip().lower())
    if err:
        print(err)
        sys.exit(1)
    print(f"已更新: id={fid} -> status={status.strip().lower()}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "list":
        cmd_list("pending")
    elif cmd == "list-all":
        cmd_list(None)
    elif cmd == "show":
        cmd_show(sys.argv[2] if len(sys.argv) == 3 else None)
    elif cmd == "approve" and len(sys.argv) == 3:
        cmd_approve(sys.argv[2])
    elif cmd == "revoke" and len(sys.argv) == 3:
        cmd_revoke(sys.argv[2])
    elif cmd == "feedback-list":
        # feedback-list [status] [type]，均选填
        cmd_feedback_list(sys.argv[2] if len(sys.argv) >= 3 else None,
                          sys.argv[3] if len(sys.argv) >= 4 else None)
    elif cmd == "feedback-show" and len(sys.argv) == 3:
        cmd_feedback_show(int(sys.argv[2]))
    elif cmd == "feedback-set" and len(sys.argv) == 4:
        cmd_feedback_set(int(sys.argv[2]), sys.argv[3])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
