from ingestion.alpaca_client import get_alpaca_client
from database.connection import get_connection
from config import SYMBOLS


# Sector information is not provided by Alpaca,
# so we define it separately for our selected companies.
COMPANY_METADATA = {
    "AAPL": {
        "company_name": "Apple Inc.",
        "sector": "Technology"
    },
    "MSFT": {
        "company_name": "Microsoft Corporation",
        "sector": "Technology"
    },
    "TSLA": {
        "company_name": "Tesla, Inc.",
        "sector": "Consumer Discretionary"
    },
    "NVDA": {
        "company_name": "NVIDIA Corporation",
        "sector": "Technology"
    }
}


def insert_metadata():
    alpaca = get_alpaca_client()
    connection = get_connection()

    try:
        # Get all assets from Alpaca
        assets = alpaca.get_all_assets()

        # Create a quick lookup by symbol
        asset_lookup = {
            asset.symbol: asset
            for asset in assets
            if asset.symbol in SYMBOLS
        }

        with connection.cursor() as cursor:

            for symbol in SYMBOLS:

                asset = asset_lookup.get(symbol)

                if asset is None:
                    print(f"{symbol}: Asset not found")
                    continue

                metadata = COMPANY_METADATA[symbol]

                # --------------------------------------------------
                # 1. SECTOR
                # --------------------------------------------------

                cursor.execute(
                    """
                    INSERT INTO sector (name)
                    VALUES (%s)
                    ON CONFLICT (name)
                    DO UPDATE SET name = EXCLUDED.name
                    RETURNING sector_id;
                    """,
                    (metadata["sector"],)
                )

                sector_id = cursor.fetchone()[0]

                # --------------------------------------------------
                # 2. COMPANY
                # --------------------------------------------------

                cursor.execute(
                    """
                    SELECT company_id
                    FROM company
                    WHERE name = %s
                    AND sector_id = %s;
                    """,
                    (
                        metadata["company_name"],
                        sector_id
                    )
                )

                company = cursor.fetchone()

                if company:
                    company_id = company[0]

                else:
                    cursor.execute(
                        """
                        INSERT INTO company (name, sector_id)
                        VALUES (%s, %s)
                        RETURNING company_id;
                        """,
                        (
                            metadata["company_name"],
                            sector_id
                        )
                    )

                    company_id = cursor.fetchone()[0]

                # --------------------------------------------------
                # 3. EXCHANGE
                # --------------------------------------------------

                exchange_name = asset.exchange.value

                cursor.execute(
                    """
                    INSERT INTO exchange (name)
                    VALUES (%s)
                    ON CONFLICT (name)
                    DO UPDATE SET name = EXCLUDED.name
                    RETURNING exchange_id;
                    """,
                    (exchange_name,)
                )

                exchange_id = cursor.fetchone()[0]

                # --------------------------------------------------
                # 4. SECURITY
                # --------------------------------------------------

                cursor.execute(
                    """
                    INSERT INTO security
                        (symbol, name, asset_class, status, company_id)
                    VALUES
                        (%s, %s, %s, %s, %s)
                    ON CONFLICT (symbol)
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        asset_class = EXCLUDED.asset_class,
                        status = EXCLUDED.status,
                        company_id = EXCLUDED.company_id
                    RETURNING security_id;
                    """,
                    (
                        asset.symbol,
                        asset.name,
                        asset.asset_class.value,
                        asset.status.value,
                        company_id
                    )
                )

                security_id = cursor.fetchone()[0]

                # --------------------------------------------------
                # 5. EXCHANGE_SECURITY
                # --------------------------------------------------

                cursor.execute(
                    """
                    INSERT INTO exchange_security
                        (exchange_id, security_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING;
                    """,
                    (
                        exchange_id,
                        security_id
                    )
                )

                print(
                    f"{symbol} inserted/updated successfully "
                    f"(security_id={security_id})"
                )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    insert_metadata()
