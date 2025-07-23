import os
import uuid
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime

app = FastAPI()

VALID_MEMBER_CODES = ["12345", "54321"]

FAKE_EVENTS = [
    {"name": "Concert Rock Việt", "date": "2025-08-15", "month": "8", "event_code": "CRV001", "available": True},
    {"name": "Hội Chợ Sách ABC", "date": "2025-09-20", "month": "9", "event_code": "HCS002", "available": True},
    {"name": "Workshop Nghệ Thuật", "date": "2025-10-01", "month": "10", "event_code": "WNA003", "available": False}
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
    if member_id in VALID_MEMBER_CODES:
        response_text = f"Xác thực mã thành viên {member_id} thành công. Vui lòng lựa chọn: 1. Đặt vé, hoặc 2. Yêu cầu khác."
        status_code = "success"
    else:
        response_text = f"Mã thành viên {member_id} không hợp lệ. Vui lòng kiểm tra lại."
        status_code = "fail"

    return build_cx_webhook_response(response_text, business_status=status_code)

@app.post("/book_tickets")
async def book_tickets(request: Request):
    request_data = await request.json()
    parameters = request_data.get('sessionInfo', {}).get('parameters', {})

    member_id = str(parameters.get('member_id', '')).lower()
    event_name = parameters.get('event_name')
    ticket_count = parameters.get('ticket_quantity')

    response_text = ""
    status_code = "fail"

    target_event = None
    for event in FAKE_EVENTS:
        if event_name and event_name.lower() in event['name'].lower():
            target_event = event
            break

    if not target_event:
        response_text = "Không tìm thấy sự kiện bạn muốn đặt vé. Vui lòng kiểm tra lại tên sự kiện."
    elif not target_event['available']:
        response_text = f"Sự kiện '{target_event['name']}' đã hết vé. Xin lỗi quý khách, không thể đặt được."
    elif not member_id or member_id not in VALID_MEMBER_CODES:
        response_text = f"Mã thành viên {member_id if member_id else 'không có'} không hợp lệ hoặc chưa được xác minh. Vui lòng cung cấp mã thành viên hợp lệ."
    elif not ticket_count or int(ticket_count) <= 0:
        response_text = "Số lượng vé không hợp lệ. Vui lòng cung cấp số lượng vé muốn đặt."
    else:
        booking_details = {
            "booking_id": str(uuid.uuid4())[:8],
            "member_code": member_id,
            "event_name": target_event['name'],
            "event_code": target_event['event_code'],
            "ticket_count": int(ticket_count),
            "booking_date": datetime.now().isoformat(),
            "note": ""
        }
        fake_bookings.append(booking_details)
        status_code = "success"
        response_text = f"Hệ thống đã thành công đặt {ticket_count} vé cho sự kiện '{target_event['name']}' với mã đặt vé {booking_details['booking_id']} cho hội viên {member_id}. Vui lòng chuyển khoản trước ngày..."

    return build_cx_webhook_response(response_text, business_status=status_code)

@app.post("/add_booking_note")
async def add_booking_note(request: Request):
    request_data = await request.json()
    parameters = request_data.get('sessionInfo', {}).get('parameters', {})

    member_id = str(parameters.get('member_id', '')).lower()
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

@app.post("/verify_event_info")
async def verify_event_info(request: Request):
    request_data = await request.json()
    parameters = request_data.get('sessionInfo', {}).get('parameters', {})

    event_name = parameters.get('event_name')
    event_date_str = parameters.get('date')
    event_month_str = parameters.get('month')

    response_text = ""
    status_code = "fail"
    found_event = None
    for event in FAKE_EVENTS:
        if event_name and event_name.lower() in event['name'].lower():
            if event_date_str and event_month_str:
                try:
                    dialogflow_date_obj = datetime.strptime(event_date_str, '%Y-%m-%dT%H:%M:%S%z')
                    event_date_formatted = dialogflow_date_obj.strftime('%Y-%m-%d')
                    fake_event_full_date = f"2025-{event['month'].zfill(2)}-{event['date'].split('-')[2].zfill(2)}"
                    if event_date_formatted == fake_event_full_date:
                        found_event = event
                        break
                except ValueError:
                    pass
            elif event_name:
                found_event = event
                break

    if found_event:
        if found_event['available']:
            response_text = f"Sự kiện '{found_event['name']}' vào ngày {found_event['date']} còn vé. Mã sự kiện là {found_event['event_code']}."
            status_code = "success"
        else:
            response_text = f"Sự kiện '{found_event['name']}' vào ngày {found_event['date']} đã hết vé. Xin lỗi quý khách."
            status_code = "fail"
    else:
        response_text = "Không tìm thấy thông tin sự kiện bạn yêu cầu. Vui lòng kiểm tra lại tên sự kiện hoặc ngày tháng."
        status_code = "fail"

    return build_cx_webhook_response(response_text, business_status=status_code)

@app.get("/status")
async def get_status():
    return {"status": "ok", "message": "Backend API is running", "current_bookings": fake_bookings}