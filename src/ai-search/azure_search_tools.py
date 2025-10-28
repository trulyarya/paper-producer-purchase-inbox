"""
Azure AI Search Index Management, Document Ingestion & Semantic Search
Handles schema creation, document upload, and hybrid search operations.
Data sourced from Airtable via airtable_tools module.
"""

# Airtable data fetchers
import os
import json
from functools import lru_cache
from typing import Any
from dotenv import load_dotenv

# Import Airtable data access functions
from crm.airtable_tools import get_all_products, get_all_customers

# Azure SDK imports
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.models import VectorizableTextQuery
from azure.search.documents.indexes.models import (
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    HnswAlgorithmConfiguration,
    VectorSearch,
    VectorSearchProfile,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
)

# Add parent directory to path for module imports
import sys

# Add parent to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


# ============================================================================
# ENVIRONMENT CONFIGURATION
# ============================================================================

load_dotenv()  # Load environment variables from .env file


def _get_env_var(name: str) -> str:
    """Return required environment variable or raise a value error early.
    Args:
        name: Name of the environment variable
    Returns:
        The value of the environment variable
    Raises:
        ValueError: If the environment variable is not set or is empty"""
    value = os.getenv(name)

    if value is None or value.strip() == "":
        raise ValueError(
            f"Environment variable '{name}' must be set and non-empty."
        )

    return value


# Azure Search settings
OPENAI_ENDPOINT = _get_env_var("AZURE_OPENAI_ENDPOINT")
OPENAI_EMBED_DEP_NAME = _get_env_var("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME")
SERVICE_ENDPOINT = _get_env_var("AZURE_SEARCH_SERVICE_ENDPOINT")

# Initialize Azure clients with managed identity
CREDENTIAL = DefaultAzureCredential()
INDEX_CLIENT = SearchIndexClient(
    endpoint=SERVICE_ENDPOINT,
    credential=CREDENTIAL
)

# Index configuration constants
INDEX_NAME_PRODUCTS = "paper-products-index"  # Products index name
INDEX_NAME_CUSTOMERS = "customer-insights-index"  # Customers index name
VECTOR_FIELD_NAME = "searchableContentVector"  # Field for vector embeddings
VECTOR_DIMENSIONS = 3072  # text-embedding-3-large dimensions

# ============================================================================
# VECTOR SEARCH CONFIGURATION
# ============================================================================


@lru_cache(maxsize=1)  # Cache to avoid rebuilding config
def _build_vector_search() -> VectorSearch:
    """
    Builds vector search configuration with HNSW algorithm.
    HNSW = Hierarchical Navigable Small World for fast ANN search.
    """
    VECTOR_ALGO_NAME = "hnsw-algo"  # Algorithm identifier

    return VectorSearch(
        algorithms=[
            # Cosine similarity by default
            HnswAlgorithmConfiguration(name=VECTOR_ALGO_NAME)
        ],
        profiles=[
            # Default PROFILE for embedding-based search
            VectorSearchProfile(
                name="embedding-profile",  # Profile name referenced in field definitions
                algorithm_configuration_name=VECTOR_ALGO_NAME,  # Links to algorithm above
                vectorizer="openai-vectorizer"  # Links to vectorizer below
            )
        ],
        vectorizers=[
            # Default VECTORIZER for embedding-based search
            AzureOpenAIVectorizer(
                vectorizer_name="openai-vectorizer",  # Vectorizer identifier
                azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                    resource_uri=OPENAI_ENDPOINT,  # Azure OpenAI service endpoint
                    deployment_id=OPENAI_EMBED_DEP_NAME,  # Model deployment name
                )
            )
        ]
    )

# ============================================================================
# SEMANTIC SEARCH CONFIGURATION
# ============================================================================


def _build_semantic_search(
    config_name: str,  # Unique config name for this index
    title_field: str,  # Primary field for semantic title
    content_fields: list[str],  # Fields with main content
    keywords_fields: list[str]  # Fields with metadata/tags
) -> SemanticSearch:
    """
    Builds semantic search configuration with field prioritization.
    Semantic ranking improves relevance using AI understanding.
    """
    return SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name=config_name,  # Referenced in search queries
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(
                        field_name=title_field),  # Most important field
                    content_fields=[SemanticField(
                        field_name=f) for f in content_fields],  # Body content
                    keywords_fields=[SemanticField(
                        field_name=f) for f in keywords_fields]  # Tags/filters
                )
            )
        ]
    )


# ============================================================================
# FIELD DEFINITIONS
# ============================================================================

def _product_fields() -> list[SearchField]:
    """
    Defines schema for paper products index.
    Maps Airtable product fields to Azure AI Search schema.
    """
    return [
        SearchField(name="sku", type=SearchFieldDataType.String,
                    key=True, filterable=True),  # Unique identifier
        SearchField(name="title", type=SearchFieldDataType.String,
                    searchable=True),  # Product name
        SearchField(name="description", type=SearchFieldDataType.String,
                    searchable=True),  # Product details
        SearchField(name="searchableContent", type=SearchFieldDataType.String,
                    searchable=True),  # Combined text
        SearchField(
            name=VECTOR_FIELD_NAME,  # Vector embeddings field
            type=SearchFieldDataType.Collection(
                SearchFieldDataType.Single),  # Array of floats
            searchable=True,  # Enable vector search
            vector_search_dimensions=VECTOR_DIMENSIONS,  # 3072 dimensions
            vector_search_profile_name="embedding-profile"  # vector config
        ),
        # Product attributes from Airtable
        SearchField(name="size", type=SearchFieldDataType.String,
                    searchable=True, filterable=True, facetable=True),  # A4, A5
        SearchField(name="gsm", type=SearchFieldDataType.Int32,
                    filterable=True, facetable=True),  # Paper weight
        SearchField(name="finish", type=SearchFieldDataType.String,
                    # Glossy, matte, etc.
                    searchable=True, filterable=True, facetable=True),
        SearchField(name="color", type=SearchFieldDataType.String,
                    filterable=True, facetable=True),  # Paper color
        SearchField(name="uom", type=SearchFieldDataType.String,
                    filterable=True, facetable=True),  # Unit of measure
        SearchField(name="unitPrice", type=SearchFieldDataType.Double,
                    filterable=True, sortable=True),  # Price per unit
        SearchField(name="qtyAvailable", type=SearchFieldDataType.Int32,
                    filterable=True, sortable=True),  # Stock quantity
        SearchField(name="active", type=SearchFieldDataType.Boolean,
                    filterable=True),  # Active status
    ]


def _customer_fields() -> list[SearchField]:
    """
    Defines schema for customer insights index.
    Maps Airtable customer fields to Azure AI Search schema.
    """
    return [
        SearchField(name="customerId", type=SearchFieldDataType.String,
                    key=True, filterable=True),  # Unique identifier
        SearchField(name="fullName", type=SearchFieldDataType.String,
                    searchable=True),  # Contact name
        SearchField(name="companyName", type=SearchFieldDataType.String,
                    searchable=True, filterable=True, facetable=True),
        SearchField(name="email", type=SearchFieldDataType.String,
                    searchable=True, filterable=True, sortable=True),
        SearchField(name="segment", type=SearchFieldDataType.String,
                    searchable=True, filterable=True, facetable=True),
        SearchField(name="city", type=SearchFieldDataType.String,
                    searchable=True, filterable=True, facetable=True),
        SearchField(name="creditLimit", type=SearchFieldDataType.Double,
                    filterable=True, sortable=True),
        SearchField(name="openAR", type=SearchFieldDataType.Double,
                    filterable=True, sortable=True),  # Accounts receivable
        SearchField(name="status", type=SearchFieldDataType.String,
                    filterable=True, facetable=True),  # Active/Inactive
        SearchField(
            name=VECTOR_FIELD_NAME,  # Vector embeddings field
            type=SearchFieldDataType.Collection(
                SearchFieldDataType.Single
            ),  # Array of floats
            searchable=True,  # Enable vector search
            vector_search_dimensions=VECTOR_DIMENSIONS,  # 3072 for embedding large
            vector_search_profile_name="embedding-profile"  # Links to vector config
        ),
    ]


# ============================================================================
# INDEX SCHEMA CREATION
# ============================================================================

def create_products_index_schema() -> None:
    """
    Creates or updates the products search index schema.
    Azure AI Search will update existing index if already present.
    """
    index = SearchIndex(
        name=INDEX_NAME_PRODUCTS,  # Index identifier
        fields=_product_fields(),  # Field definitions
        vector_search=_build_vector_search(),  # Vector search config
        semantic_search=_build_semantic_search(  # Semantic ranking config
            config_name="products-semantic-config",  # Config identifier
            title_field="title",  # Primary field
            content_fields=["description", "searchableContent"],  # Body
            keywords_fields=["sku", "size", "finish", "color"]  # Metadata
        )
    )
    INDEX_CLIENT.create_or_update_index(index)  # Upsert index
    print(f"✓ Index '{INDEX_NAME_PRODUCTS}' created/updated successfully")


def create_customer_index_schema() -> None:
    """
    Creates or updates the customers search index schema.
    Azure AI Search will update existing index if already present.
    """
    index = SearchIndex(
        name=INDEX_NAME_CUSTOMERS,  # Index identifier
        fields=_customer_fields(),  # Field definitions
        vector_search=_build_vector_search(),  # Vector search config
        semantic_search=_build_semantic_search(  # Semantic ranking config
            config_name="customers-semantic-config",  # Config identifier
            title_field="fullName",  # Primary field
            content_fields=["companyName", "email"],
            keywords_fields=["customerId", "segment", "city", "status"]
        )
    )
    INDEX_CLIENT.create_or_update_index(index)  # Upsert index
    print(f"✓ Index '{INDEX_NAME_CUSTOMERS}' created/updated successfully")

# ============================================================================
# DOCUMENT INGESTION
# ============================================================================


def upload_documents_to_index(
    index_name: str,
    documents: list[dict[str, Any]]
) -> None:
    """
    Uploads documents to specified Azure AI Search index.
    Uses batch upload for efficiency.

    Args:
        index_name: Name of the target index
        documents: list of document dictionaries to upload
    """
    search_client = SearchClient(
        endpoint=SERVICE_ENDPOINT,  # AI Search endpoint
        index_name=index_name,  # Target index
        credential=CREDENTIAL  # Managed identity
    )

    result = search_client.upload_documents(
        documents=documents)  # Batch upload
    print(f"✓ Uploaded {len(result)} documents to '{index_name}'")


def ingest_products_from_airtable() -> None:
    """
    Fetches product data from Airtable and uploads to products index.
    Transforms Airtable records into Azure AI Search document format.
    """
    records = get_all_products()  # Get all products from Airtable via airtable_tools
    documents = []  # Document accumulator

    for record in records:
        fields = record["fields"]  # Airtable fields object
        # Parse attributes
        attrs = json.loads(fields.get("Attributes JSON", "{}"))

        # Construct searchable content field for vector search:
        # This field is used for vector embeddings and full-text search
        searchable_content = (
            f"Title: {fields.get('Title', '')}. "
            f"Description: {fields.get('Description', '')}. "
            f"Size: {attrs.get('size', '')}. "
            f"Weight: {attrs.get('gsm', '')} gsm. "
            f"Finish: {attrs.get('finish', '')}. "
            f"Color: {attrs.get('color', '')}."
        )

        # Construct document dictionary for AI Search
        doc = {
            "sku": fields.get("SKU"),  # Unique identifier
            "title": fields.get("Title"),  # Product name
            "description": fields.get("Description"),  # Product details
            "searchableContent": searchable_content,  # Combined text for full-text search
            "size": attrs.get("size"),  # Paper size (A4, A5, etc.)
            "gsm": int(attrs.get("gsm", 0)),  # Paper weight
            "finish": attrs.get("finish"),  # Surface finish
            "color": attrs.get("color"),  # Paper color
            "uom": fields.get("UOM"),  # Unit of measure
            "unitPrice": float(fields.get("Unit Price", 0)),  # Price
            "qtyAvailable": int(fields.get("Qty Available", 0)),  # Stock
            "active": fields.get("Active", False),  # Active status
        }

        documents.append(doc)

    upload_documents_to_index(INDEX_NAME_PRODUCTS, documents)  # Batch upload


def ingest_customers_from_airtable() -> None:
    """
    Fetches customer data from Airtable and uploads to customers index.
    Derives segment from credit limit and extracts city from billing address.
    """
    records = get_all_customers()  # Get all customers via airtable_tools
    documents = []  # Document accumulator

    for record in records:
        fields = record["fields"]  # Airtable fields object

        # Extract city from billing address ("Street, PostalCode City, Country")
        billing_address = fields.get(
            "Billing Address", "")  # Get address string
        billing_parts = billing_address.split(", ")  # Split by comma
        city = billing_parts[2].split()[1] if len(
            billing_parts) >= 3 else ""  # Extract city

        # Derive customer segment from credit limit
        credit_limit = float(fields.get("Credit Limit", 0))  # Get credit limit
        if credit_limit >= 30000:  # High credit
            segment = "Enterprise"
        elif credit_limit >= 15000:  # Medium credit
            segment = "Mid-Market"
        else:  # Low credit
            segment = "SMB"

        doc = {
            "customerId": fields.get("Customer ID"),  # Unique identifier
            "fullName": fields.get("Name"),  # Contact name
            "companyName": fields.get("Name"),  # Company name
            "email": fields.get("Email"),  # Email address
            "segment": segment,  # Derived segment
            "city": city,  # Extracted city
            "creditLimit": credit_limit,  # Credit limit
            "openAR": float(fields.get("Open AR", 0)),  # Accounts receivable
            "status": fields.get("Status")  # Active/Inactive
        }
        documents.append(doc)

    upload_documents_to_index(INDEX_NAME_CUSTOMERS, documents)  # Batch upload


# ============================================================================
# SEARCH OPERATIONS (for Resolver Agent)
# ============================================================================

def semantic_hybrid_search(
        index_name: str,
        query_text: str,
        top: int = 5
) -> list[dict[str, Any]]:
    """
    Performs hybrid search combining vector similarity and keyword matching.
    Uses semantic ranking to reorder results by relevance.
    """
    search_client = SearchClient(
        endpoint=SERVICE_ENDPOINT,
        index_name=index_name,
        credential=CREDENTIAL
    )

    vector_query = VectorizableTextQuery(
        text=query_text,
        k_nearest_neighbors=top,
        fields=VECTOR_FIELD_NAME
    )

    results = search_client.search(
        search_text=query_text,
        vector_queries=[vector_query],
        query_type="semantic",  # Enable semantic ranking
        semantic_configuration_name=f"{index_name.split('-')[0]}-semantic-config",
        select=["*"],  # Select all fields
        top=top
    )

    return [dict(result) for result in results]


def search_customers(query: str, top: int = 5) -> list[dict[str, Any]]:
    """Searches customers by name/address. Used by resolver agent."""
    search_client = SearchClient(
        endpoint=SERVICE_ENDPOINT,
        index_name=INDEX_NAME_CUSTOMERS,
        credential=CREDENTIAL
    )

    vector_query = VectorizableTextQuery(
        text=query,
        k_nearest_neighbors=top,  # Number of nearest neighbors
        fields=VECTOR_FIELD_NAME,  # Field with vector embeddings
    )

    results = search_client.search(
        search_text=query,
        vector_queries=[vector_query],
        query_type="semantic",
        semantic_configuration_name="customers-semantic-config",
        top=top,
        select=[
            "customerId",
            "companyName",
            "email",
            "creditLimit",  # Customer credit limit available
            "openAR",  # accounts receivable: outstanding invoices
            "status"  # Active/Inactive status of customer
        ],
    )

    return [dict(r) for r in results]


def search_products(query: str, top: int = 5) -> list[dict[str, Any]]:
    """Searches products by description/specs. Used by resolver agent."""
    search_client = SearchClient(
        endpoint=SERVICE_ENDPOINT,
        index_name=INDEX_NAME_PRODUCTS,
        credential=CREDENTIAL,
    )

    vector_query = VectorizableTextQuery(
        text=query,
        k_nearest_neighbors=top,
        fields=VECTOR_FIELD_NAME
    )

    results = search_client.search(
        search_text=query,
        vector_queries=[vector_query],
        query_type="semantic",
        semantic_configuration_name="products-semantic-config",
        top=top,  # Number of results to return
        filter="active eq true",  # Only 'active' products to be returned
        select=[
            "sku",
            "title",
            "description",
            "size",
            "gsm",
            "finish",
            "color",
            "unitPrice",
            "qtyAvailable",
            "active",
        ],
    )

    return [dict(r) for r in results]


# ============================================================================
# MAIN EXECUTION
# ============================================================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print("CREATING INDEX SCHEMAS")
    print("="*60)

    create_products_index_schema()
    create_customer_index_schema()

    print("\n" + "="*60)
    print("INGESTING DOCUMENTS FROM AIRTABLE")
    print("="*60)

    # Ingest products and customers from Airtable
    ingest_products_from_airtable()
    ingest_customers_from_airtable()

    print("\n" + "="*60)
    print("EXAMPLE SEARCHES")
    print("="*60)

    print("\nProducts: 'A4 coated gloss 200gsm'")
    for i, r in enumerate(
        search_products(
            "A4 coated gloss 200gsm", top=3),
        1
    ):
        print(f"{i}. {r.get('title')} - ${r.get('unitPrice')}")

    print("\nCustomers: 'enterprise customers in Munich'")
    for i, r in enumerate(
        search_customers(
            "enterprise customers in Munich", top=3),
        1
    ):
        print(f"{i}. {r.get('companyName')} - {r.get('city')} ({r.get('segment')})")

    print("\n" + "="*60)
    print("COMPLETED")
    print("="*60 + "\n")
