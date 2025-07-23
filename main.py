import os
import uuid
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime
from fuzzywuzzy import fuzz

app = FastAPI()

VALID_MEMBER_CODES = ["12345", "54321"]

FAKE_EVENTS = [
    {"name": "Concert Rap Việt", "date": "2025-08-15", "month": "8", "event_code": "CRV001", "available": True,
     "ticket_types": ["VIP", "Standard"]},
    {"name": "Hội Chợ Sách ABC", "date": "2025-09-20", "month": "9", "event_code": "HCS002", "available": True,
     "ticket_types": ["General", "Premium"]},
    {"name": "Workshop Nghệ Thuật", "date": "2025-10-01", "month": "10", "event_code": "WNA003", "available": False,
     "ticket_types": []},
    {"name": "Black pink day 2025", "date": "2025-10-01", "month": "10", "event_code": "BPK001", "available": True,
     "ticket_types": ["Platinum", "Gold"]}
]

fake_bookings = []


def build_cx_webhook_response(text_response: str, business_status: str = "success", custom_params: dict = None):
    response_payload = {
        "fulfillmentResponse": {
            "messages": [
                {
                    "text": {
                        "text": [text_response]
                    }
                }
            ]
        }
    }

    session_info_params = {"business_status": business_status}
    if custom_params:
        session_info_params.update(custom_params)

    response_payload["sessionInfo"] = {
        "parameters": session_info_params
    }

    return JSONResponse(content=response_payload)


@app.post("/verify_member_code")
async def verify_member_code(request: Request):
    request_data = await request.json()
    parameters = request_data.get('sessionInfo', {}).get('parameters', {})

    member_id = str(parameters.get('member_id', '')).lower()

    response_text = ""
    status_code = "fail"

    custom_params = {}

    if member_id in VALID_MEMBER_CODES:
        response_text = f"Xác thực mã thành viên {member_id} thành công. Vui lòng lựa chọn: 1. Đặt vé, hoặc 2. Yêu cầu khác."
        status_code = "success"
        custom_params["verified_member_code"] = member_id
    else:
        response_text = f"Mã thành viên {member_id} không hợp lệ. Vui lòng kiểm tra lại."
        status_code = "fail"

    return build_cx_webhook_response(response_text, business_status=status_code, custom_params=custom_params)


@app.post("/validate_event_and_get_ticket_types")
async def validate_event_and_get_ticket_types(request: Request):
    request_data = await request.json()
    parameters = request_data.get('sessionInfo', {}).get('parameters', {})

    event_name_from_cx = parameters.get('event_name')
    event_date_str_from_cx = parameters.get('event_date')

    print(f"Received request for /validate_event_and_get_ticket_types:")
    print(f"  event_name from CX: '{event_name_from_cx}'")
    print(f"  event_date_str from CX: '{event_date_str_from_cx}'")

    response_text = ""
    status_code = "fail"
    is_valid_event = False
    available_ticket_types = []
    event_code = None

    found_event = None

    if not event_name_from_cx:
        response_text = "Vui lòng cung cấp tên sự kiện bạn muốn tìm."
        status_code = "fail"
        return build_cx_webhook_response(response_text, business_status=status_code)

    best_match_event = None
    best_match_score = 0
    NAME_MATCH_THRESHOLD = 75

    for event in FAKE_EVENTS:
        current_score = fuzz.ratio(event_name_from_cx.lower(), event['name'].lower())

        print(
            f"  Comparing input name='{event_name_from_cx.lower()}' with FAKE_EVENT_name='{event['name'].lower()}' (Score: {current_score})")

        if current_score >= NAME_MATCH_THRESHOLD:
            if event_date_str_from_cx:
                print(f"  Comparing input date='{event_date_str_from_cx}' with FAKE_EVENT_date='{event['date']}'")
                if event_date_str_from_cx == event['date']:
                    if current_score > best_match_score:
                        best_match_event = event
                        best_match_score = current_score
            else:
                pass

    found_event = best_match_event

    if found_event:
        if found_event['available']:
            is_valid_event = True
            available_ticket_types = found_event['ticket_types']
            event_code = found_event['event_code']
            response_text = f"Sự kiện '{found_event['name']}' vào ngày {found_event['date']} còn vé. Các loại vé có sẵn: {', '.join(available_ticket_types)}. Vui lòng chọn loại vé và số lượng bạn muốn đặt."
            status_code = "success"
        else:
            response_text = f"Sự kiện '{found_event['name']}' vào ngày {found_event['date']} đã hết vé. Xin lỗi quý khách."
            status_code = "fail"
    else:
        response_text = "Không tìm thấy thông tin sự kiện bạn yêu cầu. Vui lòng kiểm tra lại tên sự kiện hoặc ngày tháng."
        status_code = "fail"

    custom_params = {
        "is_event_valid": is_valid_event,
        "available_ticket_types": available_ticket_types,
        "event_code": event_code,
        "event_name_from_backend": found_event['name'] if found_event else None,
        "event_date_from_backend": found_event['date'] if found_event else None
    }

    return build_cx_webhook_response(response_text, business_status=status_code, custom_params=custom_params)


@app.post("/book_tickets")
async def book_tickets(request: Request):
    request_data = await request.json()
    parameters = request_data.get('sessionInfo', {}).get('parameters', {})

    member_id = str(parameters.get('verified_member_code', '')).lower()
    event_code = parameters.get('event_code')
    ticket_type = parameters.get('ticket_type', [])
    ticket_quantity = parameters.get('ticket_quantity', [])

    response_text = ""
    status_code = "fail"

    target_event = None
    if event_code:
        for event in FAKE_EVENTS:
            if event['event_code'] == event_code:
                target_event = event
                break

    if not target_event:
        response_text = "Không tìm thấy sự kiện để đặt vé. Vui lòng xác minh lại thông tin sự kiện."
    elif not target_event['available']:
        response_text = f"Sự kiện '{target_event['name']}' đã hết vé. Không thể đặt được."
    elif not member_id or member_id not in VALID_MEMBER_CODES:
        response_text = f"Mã thành viên {member_id if member_id else 'không có'} không hợp lệ hoặc chưa được xác minh. Vui lòng cung cấp mã thành viên hợp lệ."
    elif not ticket_type or not ticket_quantity or len(ticket_type) != len(ticket_quantity):  # Đã sửa
        response_text = "Thông tin loại vé hoặc số lượng không hợp lệ. Vui lòng cung cấp loại vé và số lượng bạn muốn đặt."
    else:
        all_bookings_successful = True
        booking_summary_messages = []

        for i in range(len(ticket_type)):
            current_ticket_type = ticket_type[i]
            current_ticket_quantity = int(ticket_quantity[i])

            if current_ticket_type not in target_event.get('ticket_types', []):
                booking_summary_messages.append(
                    f"Loại vé '{current_ticket_type}' không hợp lệ cho sự kiện '{target_event['name']}'.")
                all_bookings_successful = False
            elif current_ticket_quantity <= 0:
                booking_summary_messages.append(f"Số lượng vé loại '{current_ticket_type}' không hợp lệ.")
                all_bookings_successful = False
            else:
                booking_details = {
                    "booking_id": str(uuid.uuid4())[:8],
                    "member_code": member_id,
                    "event_name": target_event['name'],
                    "event_code": target_event['event_code'],
                    "event_date": target_event['date'],
                    "ticket_type": current_ticket_type,
                    "ticket_quantity": current_ticket_quantity,
                    "booking_date": datetime.now().isoformat(),
                    "note": ""
                }
                fake_bookings.append(booking_details)
                booking_summary_messages.append(f"{current_ticket_quantity} vé loại {current_ticket_type}")

        if all_bookings_successful:
            status_code = "success"
            response_text = f"Hệ thống đã thành công đặt {', '.join(booking_summary_messages)} cho sự kiện '{target_event['name']}' vào ngày {target_event['date']} cho hội viên {member_id}. Tổng cộng {sum(ticket_quantity)} vé. Vui lòng chuyển khoản trước ngày..."
        else:
            status_code = "fail"
            response_text = f"Có lỗi trong quá trình đặt vé: {'; '.join(booking_summary_messages)}. Vui lòng kiểm tra lại."

    return build_cx_webhook_response(response_text, business_status=status_code)


@app.post("/add_booking_note")
async def add_booking_note(request: Request):
    request_data = await request.json()
    parameters = request_data.get('sessionInfo', {}).get('parameters', {})

    member_id = str(parameters.get('member_code', '')).lower()
    event_code = parameters.get('event_code')
    note = parameters.get('note')

    response_text = ""
    status_code = "fail"
    booking_found = False
    if member_id and event_code and note:
        for booking in fake_bookings:
            if booking['member_code'] == member_id and booking['event_code'] == event_code:
                booking['note'] = note
                booking_found = True
                break

        if booking_found:
            response_text = "Yêu cầu đặc biệt của quý khách đã được ghi nhận. Hệ thống sẽ cố gắng đáp ứng."
            status_code = "success"
        else:
            response_text = "Không tìm thấy đặt vé phù hợp để thêm yêu cầu, hoặc thông tin chưa đủ. Vui lòng kiểm tra lại mã thành viên và mã sự kiện."
    else:
        response_text = "Thông tin không đủ để thêm ghi chú. Vui lòng cung cấp mã thành viên, mã sự kiện và nội dung ghi chú."

    return build_cx_webhook_response(response_text, business_status=status_code)


@app.get("/status")
async def get_status():
    return {"status": "ok", "message": "Backend API is running", "current_bookings": fake_bookings}