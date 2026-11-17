"""Framework knowledge the extractor needs but cannot derive from the solution itself.

Every entry is keyed by the namespace that must be imported (or written out) for the
type to resolve, so a catalog hit is a resolved symbol, not a name match. A type the
solution itself declares always wins over a catalog entry.
"""
from __future__ import annotations

# (namespace, type) -> integration category. Used for INVOKES_EXTERNAL.
EXTERNAL_TYPES: dict[tuple[str, str], str] = {
    ("System.Net.Mail", "SmtpClient"): "email/smtp",
    ("System.Net.Http", "HttpClient"): "http",
    ("System.Net", "WebClient"): "http",
    ("System.Net", "HttpWebRequest"): "http",
    ("System.Net", "WebRequest"): "http",
    ("RestSharp", "RestClient"): "http",
    ("System.Data.SqlClient", "SqlConnection"): "database/ado.net",
    ("System.Data.SqlClient", "SqlCommand"): "database/ado.net",
    ("Microsoft.Data.SqlClient", "SqlConnection"): "database/ado.net",
    ("Dapper", "SqlMapper"): "database/dapper",
    ("Rotativa", "ActionAsPdf"): "pdf-rendering",
    ("Rotativa", "ViewAsPdf"): "pdf-rendering",
    ("Rotativa", "PartialViewAsPdf"): "pdf-rendering",
    ("Rotativa", "UrlAsPdf"): "pdf-rendering",
    ("System.IO", "File"): "filesystem",
    ("System.IO", "FileStream"): "filesystem",
    ("System.IO", "StreamWriter"): "filesystem",
    ("System.ServiceModel", "ChannelFactory"): "soap/wcf",
    ("StackExchange.Redis", "ConnectionMultiplexer"): "cache/redis",
    ("Twilio.Rest.Api.V2010.Account", "MessageResource"): "sms",
    ("Amazon.S3", "AmazonS3Client"): "aws/s3",
    ("Amazon.SimpleEmail", "AmazonSimpleEmailServiceClient"): "aws/ses",
    ("Amazon.SQS", "AmazonSQSClient"): "aws/sqs",
}

# (namespace, receiver type, method) for real event publication. Used for EMITS_EVENT.
EVENT_PUBLISHERS: set[tuple[str, str, str]] = {
    ("MediatR", "IMediator", "Publish"),
    ("MediatR", "IPublisher", "Publish"),
    ("MassTransit", "IPublishEndpoint", "Publish"),
    ("MassTransit", "IBus", "Publish"),
    ("Azure.Messaging.ServiceBus", "ServiceBusSender", "SendMessageAsync"),
    ("Microsoft.Azure.ServiceBus", "ITopicClient", "SendAsync"),
    ("Amazon.EventBridge", "IAmazonEventBridge", "PutEventsAsync"),
    ("Amazon.EventBridge", "AmazonEventBridgeClient", "PutEventsAsync"),
    ("Amazon.SimpleNotificationService", "IAmazonSimpleNotificationService", "PublishAsync"),
    ("Amazon.SimpleNotificationService", "AmazonSimpleNotificationServiceClient", "PublishAsync"),
}

# Framework base types that identify the role of a solution type.
DBCONTEXT_BASES = {"DbContext", "IdentityDbContext", "ObjectContext"}
DBSET_TYPES = {"DbSet", "IDbSet"}
EF_CONFIG_BASES = {"EntityTypeConfiguration", "IEntityTypeConfiguration"}
MVC_CONTROLLER_BASES = {"Controller", "ControllerBase", "AsyncController"}
API_CONTROLLER_BASES = {"ApiController"}
HTTP_APPLICATION_BASES = {"HttpApplication"}
AUTOMAPPER_PROFILE_BASES = {"Profile"}

# EF fluent-API relationship methods -> cardinality on the configured side.
EF_RELATION_METHODS = {
    "HasRequired": "many-to-one (required)",
    "HasOptional": "many-to-one (optional)",
    "HasMany": "one-to-many",
    "HasOne": "many-to-one",
}
EF_INVERSE_METHODS = {"WithRequired", "WithOptional", "WithMany", "WithOne", "WithRequiredPrincipal",
                      "WithRequiredDependent", "WithOptionalPrincipal", "WithOptionalDependent"}

COLLECTION_TYPES = {"IList", "List", "ICollection", "Collection", "IEnumerable", "HashSet", "ISet",
                    "IReadOnlyList", "IReadOnlyCollection", "[]"}

HTTP_VERB_ATTRS = {"HttpGet": "GET", "HttpPost": "POST", "HttpPut": "PUT", "HttpDelete": "DELETE",
                   "HttpPatch": "PATCH", "HttpHead": "HEAD", "HttpOptions": "OPTIONS"}

# AngularJS $resource default actions.
NG_RESOURCE_ACTIONS = {"get": "GET", "query": "GET", "save": "POST", "remove": "DELETE", "delete": "DELETE"}
