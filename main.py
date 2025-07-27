import os
import uuid
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
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
    fulfillment_messages = []
    if text_response is not None:
        fulfillment_messages.append({
            "text": {
                "text": [text_response]
            }
        })

    response_payload = {
        "fulfillmentResponse": {
            "messages": fulfillment_messages
        }
    }

    session_info_params = {"business_status": business_status}
    if custom_params:
        session_info_params.update(custom_params)

    response_payload["sessionInfo"] = {
        "parameters": session_info_params
    }

    return JSONResponse(content=response_payload)


def parse_ticket_input(raw_input, target_type):
    """
    Xử lý đầu vào raw (có thể là string 'item1, item2' hoặc list ['item1', 'item2'])
    và chuyển đổi thành list các phần tử của target_type.
    """
    if raw_input is None:
        return []

    parsed_list = []
    if isinstance(raw_input, list):
        for item in raw_input:
            try:
                parsed_list.append(target_type(str(item).strip()))
            except ValueError:
                print(f"Warning: Could not convert list item '{item}' to {target_type.__name__}.")
                if target_type == int:
                    parsed_list.append(0)
                else:
                    pass
    elif isinstance(raw_input, str):
        items = raw_input.split(',')
        for item_str in items:
            stripped_item = item_str.strip()
            if stripped_item:
                try:
                    parsed_list.append(target_type(stripped_item))
                except ValueError:
                    print(f"Warning: Could not convert string part '{stripped_item}' to {target_type.__name__}.")
                    if target_type == int:
                        parsed_list.append(0)
                    else:
                        pass
    else:
        try:
            parsed_list.append(target_type(str(raw_input).strip()))
        except ValueError:
            print(f"Warning: Could not convert unexpected type '{raw_input}' to {target_type.__name__}.")
            if target_type == int:
                parsed_list.append(0)
            else:
                pass

    return parsed_list

@app.post("/verify_member_code")
async def verify_member_code(request: Request):
    request_data = await request.json()
    parameters = request_data.get('sessionInfo', {}).get('parameters', {})

    member_id = str(parameters.get('member_id', '')).lower()

    status_code = "fail"
    response_text = None

    custom_params = {}

    if member_id in VALID_MEMBER_CODES:
        status_code = "success"
        custom_params["club_id"] = "CLUB001"
        custom_params["member_code"] = member_id
        custom_params["name"] = "Nguyễn Văn A"
        response_text = f"Xác thực mã thành viên {member_id} thành công. Chào mừng {custom_params['name']}. Vui lòng lựa chọn: 1. Đặt vé, hoặc 2. Yêu cầu khác."
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

    candidate_events_by_date = []
    if event_date_str_from_cx:
        try:
            datetime.strptime(event_date_str_from_cx, '%Y-%m-%d')
            parsed_event_date_for_filter = event_date_str_from_cx
        except ValueError:
            try:
                dialogflow_date_obj = datetime.strptime(event_date_str_from_cx, '%Y-%m-%dT%H:%M:%S%z')
                parsed_event_date_for_filter = dialogflow_date_obj.strftime('%Y-%m-%d')
            except ValueError:
                parsed_event_date_for_filter = None

        if parsed_event_date_for_filter:
            for event in FAKE_EVENTS:
                if event['date'] == parsed_event_date_for_filter:
                    candidate_events_by_date.append(event)

        if not candidate_events_by_date and parsed_event_date_for_filter:
            response_text = f"Không tìm thấy sự kiện nào vào ngày {parsed_event_date_for_filter}. Vui lòng kiểm tra lại ngày."
            status_code = "fail"
            return build_cx_webhook_response(response_text, business_status=status_code)
    else:
        candidate_events_by_date = FAKE_EVENTS

    for event in candidate_events_by_date:
        current_score = fuzz.ratio(event_name_from_cx.lower(), event['name'].lower())

        if current_score >= NAME_MATCH_THRESHOLD:
            if event_date_str_from_cx and parsed_event_date_for_filter:
                if parsed_event_date_for_filter == event['date']:
                    if current_score > best_match_score:
                        best_match_event = event
                        best_match_score = current_score
            elif not event_date_str_from_cx:
                if current_score > best_match_score:
                    best_match_event = event
                    best_match_score = current_score

    found_event = best_match_event

    custom_params = {}
    if found_event:
        if found_event['available']:
            is_valid_event = True
            available_ticket_types = found_event['ticket_types']
            event_code = found_event['event_code']
            response_text = f"Sự kiện '{found_event['name']}' vào ngày {found_event['date']} còn vé. Các loại vé có sẵn: {', '.join(available_ticket_types)}. Vui lòng chọn loại vé và số lượng bạn muốn đặt."
            status_code = "success"
            custom_params["event_id"] = found_event['event_code']
        else:
            response_text = f"Sự kiện '{found_event['name']}' vào ngày {found_event['date']} đã hết vé. Xin lỗi quý khách."
            status_code = "fail"
    else:
        response_text = "Không tìm thấy thông tin sự kiện bạn yêu cầu. Vui lòng kiểm tra lại tên sự kiện hoặc ngày tháng."
        status_code = "fail"

    custom_params.update({
        "is_event_valid": is_valid_event,
        "available_ticket_types": available_ticket_types,
        "event_code": event_code,
        "event_name_from_backend": found_event['name'] if found_event else None,
        "event_date_from_backend": found_event['date'] if found_event else None
    })

    return build_cx_webhook_response(response_text, business_status=status_code, custom_params=custom_params)


@app.post("/book_tickets")
async def book_tickets(request: Request):
    request_data = await request.json()
    parameters = request_data.get('sessionInfo', {}).get('parameters', {})

    print(f"Received request for /book_tickets:")
    print(f"  All parameters received: {parameters}")

    member_id = str(parameters.get('member_code', '')).lower()
    event_code = parameters.get('event_code')

    ticket_type_raw = parameters.get('ticket_type')
    ticket_quantity_raw = parameters.get('ticket_quantity')

    ticket_type = parse_ticket_input(ticket_type_raw, str)
    ticket_quantity = parse_ticket_input(ticket_quantity_raw, int)

    print(f"  Extracted member_id: '{member_id}'")
    print(f"  Extracted event_code: '{event_code}'")
    print(f"  Processed ticket_type: {ticket_type}")
    print(f"  Processed ticket_quantity: {ticket_quantity}")

    response_text = ""
    status_code = "fail"

    target_event = None
    if event_code:
        for event in FAKE_EVENTS:
            if event['event_code'] == event_code:
                target_event = event
                break

    print(f"  Target event found by code: {target_event['name'] if target_event else 'None'}")

    if not target_event:
        response_text = "Không tìm thấy sự kiện để đặt vé. Vui lòng xác minh lại thông tin sự kiện."
    elif not target_event['available']:
        response_text = f"Sự kiện '{target_event['name']}' đã hết vé. Không thể đặt được."
    elif not member_id or member_id not in VALID_MEMBER_CODES:
        print(f"  Validation failed: Member ID '{member_id}' not valid.")
        response_text = f"Mã thành viên {member_id if member_id else 'không có'} không hợp lệ hoặc chưa được xác minh. Vui lòng cung cấp mã thành viên hợp lệ."
    elif not ticket_type or not ticket_quantity or len(ticket_type) != len(ticket_quantity):
        print(f"  Validation failed: Ticket types/quantities mismatch or missing.")
        print(
            f"  Ticket Type Length: {len(ticket_type) if ticket_type else 0}, Ticket Quantity Length: {len(ticket_quantity) if ticket_quantity else 0}")
        response_text = "Thông tin loại vé hoặc số lượng không hợp lệ. Vui lòng cung cấp loại vé và số lượng bạn muốn đặt."
    else:
        all_bookings_successful = True
        booking_summary_messages = []
        total_ticket_quantity_sum = 0

        current_booking_time = datetime.now()
        due_date = current_booking_time + timedelta(days=5)
        due_date_formatted = due_date.strftime('%d/%m/%Y')

        overall_booking_id = str(uuid.uuid4())[:8]

        for i in range(len(ticket_type)):
            current_ticket_type = ticket_type[i]
            current_ticket_quantity = int(ticket_quantity[i])

            print(f"  Processing item {i + 1}: Type='{current_ticket_type}', Quantity='{current_ticket_quantity}'")

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
                    "overall_booking_id": overall_booking_id,
                    "member_code": member_id,
                    "event_name": target_event['name'],
                    "event_code": target_event['event_code'],
                    "event_date": target_event['date'],
                    "ticket_type": current_ticket_type,
                    "ticket_quantity": current_ticket_quantity,
                    "booking_date": current_booking_time.isoformat(),
                    "note": ""
                }
                fake_bookings.append(booking_details)
                booking_summary_messages.append(f"{current_ticket_quantity} vé loại {current_ticket_type}")
                total_ticket_quantity_sum += current_ticket_quantity

        custom_params = {}
        if all_bookings_successful:
            status_code = "success"
            response_text = (
                f"Hệ thống đã thành công đặt {', '.join(booking_summary_messages)} cho sự kiện '{target_event['name']}' "
                f"vào ngày {target_event['date']} cho hội viên {member_id}. Tổng cộng {total_ticket_quantity_sum} vé. "
                f"Vui lòng chuyển khoản trước ngày {due_date_formatted}. Sau cuộc gọi này hệ thống sẽ gửi SMS thông tin thanh toán.")
            custom_params["booking_id"] = overall_booking_id
        else:
            status_code = "fail"
            response_text = f"Có lỗi trong quá trình đặt vé: {'; '.join(booking_summary_messages)}. Vui lòng kiểm tra lại."

    return build_cx_webhook_response(response_text, business_status=status_code, custom_params=custom_params)


@app.post("/add_booking_note")
async def add_booking_note(request: Request):
    request_data = await request.json()
    parameters = request_data.get('sessionInfo', {}).get('parameters', {})

    member_id = str(parameters.get('member_code', '')).lower()
    booking_id = parameters.get('booking_id')
    note = parameters.get('note')

    response_text = ""
    status_code = "fail"
    booking_found = False
    if member_id and booking_id and note:
        for booking in fake_bookings:
            if booking['member_code'] == member_id and booking['booking_id'] == booking_id:
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

    return build_cx_webhook_response(response_text, business_status=status_code, custom_params={})


@app.post("/faqs")
async def faq(request: Request):
    request_data = await request.json()
    parameters = request_data.get('sessionInfo', {}).get('parameters', {})

    question = parameters.get('question', "")
    print(f"User question: {question}")

    response_text = "Không tìm thấy câu trả lời. Vui lòng chờ máy, cuộc gọi sẽ được chuyển sang nhân viên hỗ trợ."

    return build_cx_webhook_response(response_text, business_status="fail", custom_params={})


@app.get("/status")
async def get_status():
    return {"status": "ok", "message": "Backend API is running", "current_bookings": fake_bookings}