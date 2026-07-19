from composio import Composio

client = Composio(api_key="ak_5ehk8JNjAshobVgU3SZS")
user_id = "default"

# Get all auth configs
configs = client.connected_accounts._client.get("/v1/auth-configs").json()

# Create links
for item in configs.get("items", []):
    app = item.get("appId")
    auth_config_id = item.get("id")
    if app in ["gmail", "github"]:
        try:
            connection = client.connected_accounts.initiate(
                user_id=user_id,
                auth_config_id=auth_config_id
            )
            print(f"Click here to connect {app.upper()}: {connection.redirectUrl}")
        except Exception as e:
            pass
            
print("Done!")
