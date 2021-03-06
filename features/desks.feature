Feature: Desks

    @auth
    Scenario: Empty desks list
        Given empty "desks"
        When we get "/desks"
        Then we get list with 0 items

    @auth
    @notification
    Scenario: Create new desk
        Given empty "users"
        Given empty "desks"
        When we post to "users"
            """
            {"username": "foo", "email": "foo@bar.com", "is_active": true}
            """
        When we post to "/desks"
            """
            {"name": "Sports Desk", "members": [{"user": "#users._id#"}]}
            """
        And we get "/desks"
        Then we get list with 1 items
            """
            {"_items": [{"name": "Sports Desk", "members": [{"user": "#users._id#"}]}]}
            """
        Then we get notifications
            """
            [{"event": "desk", "extra": {"created": 1, "desk_id": "#desks._id#"}}]
            """
        When we get the default incoming stage
        And we delete latest
        Then we get error 403
        """
        {"_status": "ERR", "_message": "Deleting default stages is not allowed."}
        """

	@auth
    @notification
	Scenario: Update desk
	    Given empty "desks"
		When we post to "/desks"
            """
            {"name": "Sports Desk"}
            """
		And we patch latest
			 """
            {"name": "Sports Desk modified"}
             """
		Then we get updated response
        Then we get notifications
            """
            [{"event": "desk", "extra": {"updated": 1, "desk_id": "#desks._id#"}}]
            """

	@auth
    @notification
	Scenario: Delete desk
		Given "desks"
			"""
			[{"name": "test_desk1"}]
			"""
		When we post to "/desks"
        	"""
            [{"name": "test_desk2"}]
            """
        And we delete latest
        Then we get notifications
        """
        [{"event": "desk", "extra": {"deleted": 1, "desk_id": "#desks._id#"}}]
        """
        Then we get deleted response

	@auth
	Scenario: Desk name must be unique.
	    Given empty "desks"
		When we post to "/desks"
            """
            {"name": "Sports Desk"}
            """
        Then we get OK response
		When we post to "/desks"
			 """
            {"name": "Sports Desk"}
             """
		Then we get response code 400
		When we post to "/desks"
			 """
            {"name": "Sports Desk 2"}
             """
        Then we get OK response
		When we patch "/desks/#desks._id#"
			 """
            {"name": "Sports Desk"}
             """
		Then we get response code 400