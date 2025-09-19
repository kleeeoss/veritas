    forgery_score = None
    try:
        # Re-open the saved file to send to the model server
        with open(file_path, "rb") as f:
            files = {"file": (file.filename, f, file.content_type)}
            response = requests.post(MODEL_SERVER_URL, files=files)
            response.raise_for_status() # Raises an exception for 4XX/5XX errors
            
            # Get the score from the model server's response
            data = response.json()
            forgery_score = data.get("forgery_score")

    except requests.exceptions.RequestException as e:
        # If the model server is down or returns an error
        raise HTTPException(status_code=503, detail=f"Model service unavailable: {e}")

    return VerificationResponse(
        filename=file.filename,
        content_type=file.content_type,
        message="File processed successfully.",
        ocr_data={"status": "pending"},
        forgery_score=forgery_score
    )
